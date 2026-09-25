use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3::exceptions::{PyValueError, PyRuntimeError};
use serde_json::Value as JsonValue;
use std::sync::{Arc, Mutex};

use braid_core::{
    BraidEngine,
    Capability, Policy, PolicySnapshot, PolicyRule,
    crypto::{from_hex, pub_key_hex, hash as core_hash, hex as core_hex},
    engine::node_is_proven,
};

/// Python wrapper for BraidEngine
#[pyclass]
struct PyBraidEngine {
    engine: Arc<Mutex<BraidEngine>>,
}

#[pymethods]
impl PyBraidEngine {
    #[new]
    fn new(log_path: &str, signer_hex: &str) -> PyResult<Self> {
        let signer_bytes = from_hex(signer_hex).map_err(|e| PyValueError::new_err(format!("Invalid signer hex: {}", e)))?;
        if signer_bytes.len() != 32 {
            return Err(PyValueError::new_err("Signer must be 32 bytes"));
        }
        let mut signer_arr = [0u8; 32];
        signer_arr.copy_from_slice(&signer_bytes);
        let signing_key = ed25519_dalek::SigningKey::from_bytes(&signer_arr);
        
        let engine = BraidEngine::new(log_path, signing_key)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to create engine: {}", e)))?;
        
        Ok(Self {
            engine: Arc::new(Mutex::new(engine)),
        })
    }

    #[staticmethod]
    fn generate_signer() -> PyResult<String> {
        use rand::rngs::OsRng;
        let signing_key = ed25519_dalek::SigningKey::generate(&mut OsRng);
        Ok(pub_key_hex(&signing_key.verifying_key()))
    }

    fn id_hex(&self) -> String {
        self.engine.lock().unwrap().id_hex()
    }

    fn register_snapshot(&self, snap: PyPolicySnapshot) -> PyResult<()> {
        self.engine.lock().unwrap().register_snapshot(snap.0);
        Ok(())
    }

    fn snapshot_cids(&self) -> Vec<String> {
        // Use read to expose registered snapshot cids via a write-capable view.
        // The engine exposes no public snapshot list; return those that are
        // known through the write path is not available, so expose empty set.
        Vec::new()
    }

    #[pyo3(signature = (cap, snapshot_cid, op, target, payload))]
    fn write(&self, cap: &str, snapshot_cid: &str, op: &str, target: &str, payload: &Bound<'_, PyDict>) -> PyResult<PyWriteReceipt> {
        let capability = Capability::parse(cap);
        let json_payload: JsonValue = pythonize::depythonize(&payload.as_borrowed())
            .map_err(|e| PyValueError::new_err(format!("Invalid payload: {}", e)))?;
        
        let receipt = self.engine.lock().unwrap()
            .write(&capability, snapshot_cid, op, target, json_payload)
            .map_err(|e| PyRuntimeError::new_err(format!("Write failed: {}", e)))?;
        Ok(PyWriteReceipt(receipt))
    }

    #[pyo3(signature = (base_cap, base_snapshot_cid, escalation_cap, escalation_snapshot_cid, op, target, payload))]
    fn write_escalated(&self, base_cap: &str, base_snapshot_cid: &str, escalation_cap: &str, escalation_snapshot_cid: &str, op: &str, target: &str, payload: &Bound<'_, PyDict>) -> PyResult<PyWriteReceipt> {
        let base_capability = Capability::parse(base_cap);
        let escalation_capability = Capability::parse(escalation_cap);
        let json_payload: JsonValue = pythonize::depythonize(&payload.as_borrowed())
            .map_err(|e| PyValueError::new_err(format!("Invalid payload: {}", e)))?;
        let escalation = braid_core::engine::Escalation {
            cap: &escalation_capability,
            snapshot_cid: escalation_snapshot_cid,
        };
        
        let receipt = self.engine.lock().unwrap()
            .write_escalated(&base_capability, base_snapshot_cid, &escalation, op, target, json_payload)
            .map_err(|e| PyRuntimeError::new_err(format!("Escalated write failed: {}", e)))?;
        Ok(PyWriteReceipt(receipt))
    }

    fn read(&self, cid: &str) -> PyResult<Option<PyNode>> {
        let node = self.engine.lock().unwrap().log.get(cid)
            .map(|n| PyNode(n.clone()));
        Ok(node)
    }

    fn head(&self) -> PyResult<Option<PyNode>> {
        let node = self.engine.lock().unwrap().log.head()
            .map(|n| PyNode(n.clone()));
        Ok(node)
    }

    fn prove(&self, cid: &str) -> bool {
        self.engine.lock().unwrap().log.verify(cid)
    }

    #[pyo3(signature = (cap, snapshot_cid, desire, target, context, weight))]
    fn intent_submit(&self, cap: &str, snapshot_cid: &str, desire: &str, target: &str, context: &Bound<'_, PyDict>, weight: u64) -> PyResult<PyWriteReceipt> {
        let capability = Capability::parse(cap);
        let json_context: JsonValue = pythonize::depythonize(&context.as_borrowed())
            .map_err(|e| PyValueError::new_err(format!("Invalid context: {}", e)))?;
        let payload = serde_json::json!({
            "desire": desire,
            "target": target,
            "context": json_context,
            "weight": weight
        });
        let receipt = self.engine.lock().unwrap()
            .write(&capability, snapshot_cid, "write:intent", target, payload)
            .map_err(|e| PyRuntimeError::new_err(format!("Intent submit failed: {}", e)))?;
        Ok(PyWriteReceipt(receipt))
    }

    #[pyo3(signature = (cap, snapshot_cid))]
    fn intent_view(&self, cap: &str, snapshot_cid: &str) -> PyResult<PyIntentView> {
        use braid_core::intent::IntentStrand;
        let capability = Capability::parse(cap);
        let engine = self.engine.lock().unwrap();
        let view = IntentStrand::from_ledger(&engine, &capability, snapshot_cid);
        Ok(PyIntentView {
            submitted: view.submitted,
            open: view.open,
            resolved: view.resolved,
            pending_count: view.pending_count,
            intents: view.intents.iter().map(|i| {
                serde_json::json!({
                    "cid": i.cid,
                    "depth": i.depth,
                    "target": i.target,
                    "desire": i.desire,
                    "context": i.context,
                    "weight": i.weight,
                    "signer": i.signer,
                    "provenance_ok": i.provenance_ok,
                    "status": match i.status {
                        braid_core::intent::IntentStatus::Open => "open",
                        braid_core::intent::IntentStatus::Resolved => "resolved",
                    },
                })
            }).collect(),
        })
    }
}

/// Python wrapper for PolicySnapshot
#[pyclass]
#[derive(Clone)]
struct PyPolicySnapshot(PolicySnapshot);

#[pymethods]
impl PyPolicySnapshot {
    #[new]
    #[pyo3(signature = (cid, rules, signer, default_deny, name, version))]
    fn new(cid: String, rules: Vec<PyPolicyRule>, signer: String, default_deny: bool, name: String, version: u32) -> Self {
        let rules: Vec<PolicyRule> = rules.into_iter().map(|r| r.0).collect();
        let policy = Policy {
            name,
            version,
            default_deny,
            rules,
        };
        Self(PolicySnapshot {
            cid,
            policy,
            signer,
            signature: String::new(),
        })
    }

    fn evaluate(&self, cap: &str) -> bool {
        let capability = Capability::parse(cap);
        self.0.evaluate(&capability)
    }
}

/// Python wrapper for PolicyRule
#[pyclass]
#[derive(Clone)]
struct PyPolicyRule(PolicyRule);

#[pymethods]
impl PyPolicyRule {
    #[new]
    #[pyo3(signature = (allow, capability=None, match_resource=None, match_action=None, match_target=None))]
    fn new(allow: bool, capability: Option<String>, match_resource: Option<String>, match_action: Option<String>, match_target: Option<String>) -> Self {
        Self(PolicyRule {
            allow,
            capability,
            match_resource,
            match_action,
            match_target,
        })
    }
}

/// Python wrapper for WriteReceipt
#[pyclass]
struct PyWriteReceipt(braid_core::WriteReceipt);

#[pymethods]
impl PyWriteReceipt {
    #[getter]
    fn ok(&self) -> bool { self.0.ok }
    #[getter]
    fn cid(&self) -> String { self.0.cid.clone() }
    #[getter]
    fn depth(&self) -> u64 { self.0.depth }
    #[getter]
    fn proof_hops(&self) -> usize { self.0.proof_hops }
    #[getter]
    fn escalated(&self) -> bool { self.0.escalated }
    #[getter]
    fn precommit_verified(&self) -> bool { self.0.precommit_verified }
    
    fn __repr__(&self) -> String {
        format!("WriteReceipt(cid={}, depth={}, hops={}, escalated={}, verified={})", 
            self.0.cid, self.0.depth, self.0.proof_hops, self.0.escalated, self.0.precommit_verified)
    }
}

/// Python wrapper for Node
#[pyclass]
struct PyNode(braid_core::Node);

#[pymethods]
impl PyNode {
    #[getter]
    fn cid(&self) -> String { self.0.cid.clone() }
    #[getter]
    fn depth(&self) -> u64 { self.0.depth }
    #[getter]
    fn signer(&self) -> String { self.0.signer.clone() }
    #[getter]
    fn op(&self) -> String { self.0.body.op.clone() }
    #[getter]
    fn target(&self) -> String { self.0.body.target.clone() }
    #[getter]
    fn payload<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        Ok(pythonize::pythonize(py, &self.0.body.payload)?)
    }
    #[getter]
    fn prev(&self) -> Option<String> { self.0.body.prev.clone() }
    #[getter]
    fn is_proven(&self) -> bool { node_is_proven(&self.0) }
    
    fn __repr__(&self) -> String {
        format!("Node(cid={}, depth={}, op={}, target={})", 
            self.0.cid, self.0.depth, self.0.body.op, self.0.body.target)
    }
}

/// Python wrapper for IntentView
#[pyclass]
struct PyIntentView {
    submitted: usize,
    open: usize,
    resolved: usize,
    pending_count: usize,
    intents: Vec<JsonValue>,
}

#[pymethods]
impl PyIntentView {
    #[getter]
    fn submitted(&self) -> usize { self.submitted }
    #[getter]
    fn open(&self) -> usize { self.open }
    #[getter]
    fn resolved(&self) -> usize { self.resolved }
    #[getter]
    fn pending_count(&self) -> usize { self.pending_count }
    #[getter]
    fn intents<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        Ok(pythonize::pythonize(py, &self.intents)?)
    }
}

/// Python wrapper for Capability
#[pyclass]
struct PyCapability(Capability);

#[pymethods]
impl PyCapability {
    #[staticmethod]
    fn parse(s: &str) -> Self {
        Self(Capability::parse(s))
    }
    
    #[getter]
    fn resource(&self) -> String { self.0.resource.clone() }
    #[getter]
    fn action(&self) -> String { self.0.action.clone() }
    #[getter]
    fn target(&self) -> String { self.0.target.clone() }
    
    fn __str__(&self) -> String { self.0.to_string() }
    
    fn grants(&self, other: &PyCapability) -> bool {
        self.0.grants(&other.0)
    }
}

/// Crypto utilities
#[pyfunction]
fn hash_data(data: &[u8]) -> String {
    let digest = core_hash(data);
    core_hex(&digest)
}

#[pyfunction]
fn verify_signature(signer_hex: &str, message: &[u8], signature_hex: &str) -> bool {
    let key_bytes = match from_hex(signer_hex) {
        Ok(bytes) if bytes.len() == 32 => bytes,
        _ => return false,
    };
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&key_bytes);
    let vk = match ed25519_dalek::VerifyingKey::from_bytes(&arr) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let sig_bytes = match from_hex(signature_hex) {
        Ok(b) if b.len() == 64 => b,
        _ => return false,
    };
    let mut sig_arr = [0u8; 64];
    sig_arr.copy_from_slice(&sig_bytes);
    braid_core::crypto::verify(&vk, message, &sig_arr).is_ok()
}

/// Module initialization
#[pymodule]
fn braid_python(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyBraidEngine>()?;
    m.add_class::<PyPolicySnapshot>()?;
    m.add_class::<PyPolicyRule>()?;
    m.add_class::<PyWriteReceipt>()?;
    m.add_class::<PyNode>()?;
    m.add_class::<PyIntentView>()?;
    m.add_class::<PyCapability>()?;
    m.add_function(wrap_pyfunction!(hash_data, m)?)?;
    m.add_function(wrap_pyfunction!(verify_signature, m)?)?;
    Ok(())
}
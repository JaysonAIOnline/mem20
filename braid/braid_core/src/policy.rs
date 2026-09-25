//! Braid policy: capability tokens + policy snapshots + evaluation.
//!
//! Three strands, one rope (final dream): door1 witness carries small scoped
//! caps (`read:timeline`, `write:note`, `invoke:tool`); door2 godmode carries
//! `read:*/write:*/invoke:*/admin:*`; door3 v-world carries `read:world`,
//! `invoke:spatial`. Every op commits via a braided triplet: (capability
//! token, policy snapshot at commit time, audit pre-commitment).

use serde::{Deserialize, Serialize};

/// A capability: `resource:action[:target]`, with `*` as wildcard.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct Capability {
    pub resource: String,
    pub action: String,
    #[serde(default = "default_wild")]
    pub target: String,
}

fn default_wild() -> String {
    "*".into()
}

impl Capability {
    pub fn new(resource: &str, action: &str, target: &str) -> Self {
        Self {
            resource: resource.into(),
            action: action.into(),
            target: target.into(),
        }
    }

    /// Parse `resource:action:target` (missing parts default to `*`).
    pub fn parse(s: &str) -> Self {
        let parts: Vec<&str> = s.split(':').collect();
        Self {
            resource: parts.first().map_or("*", |v| *v).into(),
            action: parts.get(1).copied().unwrap_or("*").into(),
            target: parts.get(2).copied().unwrap_or("*").into(),
        }
    }

    /// Does `self` grant `other`? One-directional, wildcard-aware on each axis:
/// only the GRANTING side (`self`) may use `*`. A narrow rule must never
/// grant a broader token (`write:note:*` must NOT grant `write:*:*`) — that
/// is the escalation boundary in m4: a widcard token is only ever produced by
/// a wildcard rule under a human-signed escalation snapshot.
    pub fn grants(&self, other: &Capability) -> bool {
        let r = self.resource == "*" || self.resource == other.resource;
        let a = self.action == "*" || self.action == other.action;
        let t = self.target == "*" || self.target == other.target;
        r && a && t
    }

    /// Does `self` cover a concrete op? Ops travel full-form (`admin:destroy`,
    /// `write:note`); the action axis is the second segment. Action `*` covers
    /// every op.
    pub fn action_grants_op(&self, op: &str) -> bool {
        let op_action = op
            .strip_prefix(':')
            .unwrap_or(op)
            .split(':')
            .nth(1)
            .unwrap_or(op);
        self.action == "*" || self.action == op_action || self.action == op
    }

    /// Does `self`'s resource equal `res` (wildcard matches all)?
    pub fn resource_matches(&self, res: &str) -> bool {
        self.resource == "*" || self.resource == res
    }
}

impl std::fmt::Display for Capability {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}:{}:{}", self.resource, self.action, self.target)
    }
}

/// A single allow/deny rule inside a policy document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyRule {
    pub allow: bool,
    pub capability: Option<String>,
    #[serde(default)]
    pub match_resource: Option<String>,
    #[serde(default)]
    pub match_action: Option<String>,
    #[serde(default)]
    pub match_target: Option<String>,
}

/// A named, versioned, frozen policy document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Policy {
    pub name: String,
    pub version: u32,
    #[serde(default = "default_true")]
    pub default_deny: bool,
    #[serde(default)]
    pub rules: Vec<PolicyRule>,
}

fn default_true() -> bool {
    true
}

/// The frozen state the policy was in when an op was evaluated — one of the
/// three braided-triplet strands.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicySnapshot {
    pub cid: String,
    pub signer: String,
    #[serde(default)]
    pub signature: String,
    pub policy: Policy,
}

impl PolicySnapshot {
    /// Evaluate the requested capability under this snapshot's rules.
    pub fn evaluate(&self, cap: &Capability) -> bool {
        let mut granted = false;
        for rule in &self.policy.rules {
            let matches = match &rule.capability {
                Some(token) => Capability::parse(token).grants(cap),
                None => {
                    let probe = Capability::new(
                        rule.match_resource.as_deref().unwrap_or("*"),
                        rule.match_action.as_deref().unwrap_or("*"),
                        rule.match_target.as_deref().unwrap_or("*"),
                    );
                    probe.grants(cap)
                }
            };
            if matches {
                granted = rule.allow;
            }
        }
        if self.policy.default_deny {
            granted
        } else {
            true
        }
    }

    /// Evaluate a raw capability string (convenience).
    pub fn evaluate_str(&self, cap: &str) -> bool {
        self.evaluate(&Capability::parse(cap))
    }
}

/// Parse the genesis `policy_seed.toml` into an untrusted `Policy`.
pub fn policy_from_toml(toml_str: &str) -> Result<Policy, String> {
    toml::from_str(toml_str).map_err(|e| format!("policy parse error: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seed() -> Policy {
        policy_from_toml(
            r#"
name = "genesis"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:note:*"

[[rules]]
allow = true
capability = "write:*:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#,
        )
        .unwrap()
    }

    #[test]
    fn wildcard_grants_scoped() {
        let full = Capability::new("*", "*", "*");
        assert!(full.grants(&Capability::new("read", "timeline", "root")));
        let scoped = Capability::new("read", "timeline", "root");
        assert!(!scoped.grants(&Capability::new("write", "timeline", "root")));
    }

    #[test]
    fn snapshot_evaluates_caps() {
        let p = seed();
        let snap = PolicySnapshot {
            cid: "test".into(),
            signer: "test".into(),
            signature: String::new(),
            policy: p,
        };
        assert!(snap.evaluate_str("read:timeline:root"));
        assert!(snap.evaluate_str("write:note:alice"));
        assert!(!snap.evaluate_str("admin:everything:root"));
        // default_deny: an unmatched cap is refused
        assert!(!snap.evaluate_str("invoke:shell:root"));
    }
}
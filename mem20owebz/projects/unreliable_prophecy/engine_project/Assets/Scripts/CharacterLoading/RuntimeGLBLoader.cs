using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace UnreliableProphecy
{
    /// <summary>
    /// Runtime GLB loader capable of parsing binary glTF files and
    /// reconstructing Unity meshes, materials, and transforms.
    /// Supports:
    ///   - GLB v2 container format
    ///   - Multiple meshes / primitives
    ///   - POSITION, NORMAL, TEXCOORD_0, COLOR_0, JOINTS_0, WEIGHTS_0 accessors
    ///   - Sparse accessors
    ///   - Embedded buffer views (GLB binary chunk + base64 data URIs)
    ///   - Skin binding to bones
    ///   - Translation / Rotation / Scale / TRS-matrix node transforms
    /// </summary>
    public static class RuntimeGLBLoader
    {
        // ── GLTF JSON classes ──────────────────────────────────────────
        [Serializable]
        public class GltfRoot
        {
            public Asset asset;
            public int scene;
            public Scene[] scenes;
            public Node[] nodes;
            public Mesh[] meshes;
            public Accessor[] accessors;
            public BufferView[] bufferViews;
            public Buffer[] buffers;
            public Material[] materials;
            public Skin[] skins;
            public Texture[] textures;
            public Image[] images;
            public Sampler[] samplers;
            public Animation[] animations;
        }

        [Serializable]
        public class Asset { public string version; public string generator; }

        [Serializable]
        public class Scene { public string name; public int[] nodes; }

        [Serializable]
        public class Node
        {
            public string name;
            public int[] children;
            public int mesh = -1;
            public int skin = -1;
            public int camera = -1;
            public float[] matrix;
            public float[] translation;
            public float[] rotation;
            public float[] scale;
        }

        [Serializable]
        public class Mesh
        {
            public string name;
            public Primitive[] primitives;
            public float[] weights;
        }

        [Serializable]
        public class Primitive
        {
            public Dictionary<string, int> attributes;
            public int indices = -1;
            public int material = -1;
            public int mode = 4; // TRIANGLES
        }

        [Serializable]
        public class Accessor
        {
            public int bufferView = -1;
            public int componentType;
            public int count;
            public string type;
            public int byteOffset;
            public float[] min;
            public float[] max;
            public SparseAccessor sparse;
        }

        [Serializable]
        public class SparseAccessor
        {
            public int count;
            public SparseIndices indices;
            public SparseValues values;
        }

        [Serializable]
        public class SparseIndices { public int bufferView; public int componentType; public int byteOffset; }

        [Serializable]
        public class SparseValues { public int bufferView; public int byteOffset; }

        [Serializable]
        public class BufferView
        {
            public int buffer;
            public int byteOffset;
            public int byteLength;
            public int byteStride;
            public int target;
        }

        [Serializable]
        public class Buffer { public int byteLength; public string uri; }

        [Serializable]
        public class Material
        {
            public string name;
            public PBRMetallicRoughness pbrMetallicRoughness;
            public bool doubleSided;
            public string alphaMode;
            public float alphaCutoff;
        }

        [Serializable]
        public class PBRMetallicRoughness
        {
            public float[] baseColorFactor;
            public int baseColorTexture = -1;
            public float metallicFactor = 1f;
            public float roughnessFactor = 1f;
        }

        [Serializable]
        public class Texture { public int source; public int sampler; }

        [Serializable]
        public class Image { public string uri; public string mimeType; }

        [Serializable]
        public class Sampler { public int magFilter; public int minFilter; }

        [Serializable]
        public class Skin
        {
            public string name;
            public int inverseBindMatrices;
            public int[] joints;
            public int skeleton = -1;
        }

        [Serializable]
        public class Animation { }

        // ── Public load API ───────────────────────────────────────────

        /// <summary>
        /// Parse a GLB file from raw bytes.
        /// Returns the root GameObject of the loaded scene.
        /// </summary>
        public static GameObject LoadFromBytes(byte[] glbData, string baseName = "GLBModel")
        {
            if (glbData == null || glbData.Length < 20)
                throw new ArgumentException("GLB data too short");

            // Parse GLB header
            uint magic = ToUInt32(glbData, 0);
            uint version = ToUInt32(glbData, 4);
            uint totalLength = ToUInt32(glbData, 8);

            if (magic != 0x46546C67u)
                throw new InvalidDataException("Not a GLB file (bad magic number)");

            if (version != 2)
                throw new NotSupportedException($"GLB version {version} not supported (only v2)");

            if (totalLength > glbData.Length)
                throw new InvalidDataException($"GLB header says {totalLength} bytes but data is only {glbData.Length}");

            // Parse JSON chunk
            uint jsonLen = ToUInt32(glbData, 12);
            uint jsonType = ToUInt32(glbData, 16);
            if (jsonType != 0x4E4F534Au) // "JSON"
                throw new InvalidDataException("First GLB chunk is not JSON");

            string jsonStr = Encoding.UTF8.GetString(glbData, 20, (int)jsonLen);
            var root = JsonUtility.FromJson<GltfRoot>(jsonStr);

            // Parse BIN chunk (if any)
            byte[] binChunk = null;
            int binOffset = 20 + (int)jsonLen;
            if (binOffset + 8 <= glbData.Length)
            {
                uint binLen = ToUInt32(glbData, binOffset);
                uint binType = ToUInt32(glbData, binOffset + 4);
                if (binType == 0x004E4942u) // "BIN\0"
                {
                    binChunk = new byte[binLen];
                    Buffer.BlockCopy(glbData, binOffset + 8, binChunk, 0, (int)binLen);
                }
            }

            // Resolve all buffers (embedded, data URIs, or from BIN chunk)
            var resolvedBuffers = ResolveBuffers(root, binChunk);

            // Build the scene
            return BuildScene(root, resolvedBuffers, baseName);
        }

        // ── Buffer resolution ──────────────────────────────────────────

        static byte[][] ResolveBuffers(GltfRoot root, byte[] binChunk)
        {
            var result = new byte[root.buffers.Length][];
            for (int i = 0; i < root.buffers.Length; i++)
            {
                var buf = root.buffers[i];
                if (!string.IsNullOrEmpty(buf.uri))
                {
                    if (buf.uri.StartsWith("data:"))
                    {
                        // Data URI (base64)
                        int commaIdx = buf.uri.IndexOf(',');
                        string base64 = buf.uri.Substring(commaIdx + 1);
                        result[i] = Convert.FromBase64String(base64);
                    }
                    else
                    {
                        // External file reference – not supported in runtime loader
                        Debug.LogWarning($"[RuntimeGLBLoader] External buffer '{buf.uri}' not supported; treating as empty");
                        result[i] = new byte[buf.byteLength];
                    }
                }
                else if (i == 0 && binChunk != null)
                {
                    result[i] = binChunk;
                }
                else
                {
                    result[i] = new byte[buf.byteLength];
                }
            }
            return result;
        }

        // ── Scene building ─────────────────────────────────────────────

        static GameObject BuildScene(GltfRoot root, byte[][] buffers, string baseName)
        {
            var go = new GameObject(baseName);

            // Build mesh data cache (shared across nodes)
            var meshCache = new Dictionary<int, Mesh>();
            var materialCache = new Dictionary<int, UnityEngine.Material>();

            // Pre-build materials
            if (root.materials != null)
            {
                for (int i = 0; i < root.materials.Length; i++)
                    materialCache[i] = BuildMaterial(root.materials[i]);
            }

            // Create all nodes
            var nodeGOs = new GameObject[root.nodes.Length];
            var nodeWorldMats = new Matrix4x4[root.nodes.Length];

            for (int i = 0; i < root.nodes.Length; i++)
            {
                var node = root.nodes[i];
                nodeGOs[i] = new GameObject(string.IsNullOrEmpty(node.name) ? $"Node_{i}" : node.name);
                nodeGOs[i].transform.SetParent(go.transform, false);

                // Apply transform
                if (node.matrix != null && node.matrix.Length == 16)
                {
                    var m = new Matrix4x4();
                    for (int k = 0; k < 16; k++)
                        m[k] = node.matrix[k];
                    nodeGOs[i].transform.localPosition = m.GetColumn(3);
                    nodeGOs[i].transform.localRotation = Quaternion.LookRotation(m.GetColumn(2), m.GetColumn(1));
                    nodeGOs[i].transform.localScale = new Vector3(m.GetColumn(0).magnitude, m.GetColumn(1).magnitude, m.GetColumn(2).magnitude);
                }
                else
                {
                    if (node.translation != null && node.translation.Length >= 3)
                        nodeGOs[i].transform.localPosition = new Vector3(node.translation[0], node.translation[1], node.translation[2]);
                    if (node.rotation != null && node.rotation.Length >= 4)
                        nodeGOs[i].transform.localRotation = new Quaternion(node.rotation[0], node.rotation[1], node.rotation[2], node.rotation[3]);
                    if (node.scale != null && node.scale.Length >= 3)
                        nodeGOs[i].transform.localScale = new Vector3(node.scale[0], node.scale[1], node.scale[2]);
                }
            }

            // Parent nodes
            for (int i = 0; i < root.nodes.Length; i++)
            {
                if (root.nodes[i].children != null)
                {
                    foreach (int childIdx in root.nodes[i].children)
                    {
                        if (childIdx >= 0 && childIdx < nodeGOs.Length)
                            nodeGOs[childIdx].transform.SetParent(nodeGOs[i].transform, false);
                    }
                }
            }

            // Build meshes and assign to nodes
            for (int i = 0; i < root.nodes.Length; i++)
            {
                if (root.nodes[i].mesh >= 0)
                {
                    var meshObj = BuildMeshObject(root, root.nodes[i].mesh, buffers, meshCache, materialCache);
                    if (meshObj != null)
                    {
                        meshObj.transform.SetParent(nodeGOs[i].transform, false);
                        meshObj.transform.localPosition = Vector3.zero;
                        meshObj.transform.localRotation = Quaternion.identity;
                        meshObj.transform.localScale = Vector3.one;
                    }
                }

                // Handle skin binding
                if (root.nodes[i].skin >= 0 && root.skins != null && root.nodes[i].skin < root.skins.Length)
                {
                    BuildSkin(root, root.nodes[i].skin, nodeGOs, i, buffers);
                }
            }

            // Instantiate scene root nodes
            if (root.scenes != null && root.scenes.Length > 0)
            {
                var scene = root.scenes[root.scene];
                foreach (int rootNodeIdx in scene.nodes)
                {
                    if (rootNodeIdx >= 0 && rootNodeIdx < nodeGOs.Length)
                        nodeGOs[rootNodeIdx].transform.SetParent(go.transform, false);
                }
            }
            else
            {
                // No scene defined – reparent all unparented nodes
                for (int i = 0; i < nodeGOs.Length; i++)
                    if (nodeGOs[i].transform.parent == go.transform)
                        nodeGOs[i].transform.SetParent(go.transform, false);
            }

            return go;
        }

        // ── Mesh building ──────────────────────────────────────────────

        static GameObject BuildMeshObject(GltfRoot root, int meshIdx, byte[][] buffers,
            Dictionary<int, Mesh> meshCache, Dictionary<int, UnityEngine.Material> materialCache)
        {
            var gltfMesh = root.meshes[meshIdx];
            var go = new GameObject(string.IsNullOrEmpty(gltfMesh.name) ? $"Mesh_{meshIdx}" : gltfMesh.name);

            foreach (var prim in gltfMesh.primitives)
            {
                var mesh = BuildMesh(root, prim, buffers);
                if (mesh == null) continue;

                var primGO = new GameObject("Primitive");
                primGO.transform.SetParent(go.transform, false);

                var mf = primGO.AddComponent<MeshFilter>();
                mf.mesh = mesh;

                var mr = primGO.AddComponent<MeshRenderer>();
                if (prim.material >= 0 && materialCache.ContainsKey(prim.material))
                    mr.material = materialCache[prim.material];
                else
                {
                    var defaultMat = new Material(Shader.Find("Standard"));
                    if (defaultMat != null)
                    {
                        defaultMat.color = Color.white;
                        mr.material = defaultMat;
                    }
                }
            }

            return go;
        }

        static Mesh BuildMesh(GltfRoot root, Primitive prim, byte[][] buffers)
        {
            var mesh = new Mesh();

            // Read attributes
            bool hasPositions = prim.attributes.TryGetValue("POSITION", out int posIdx);
            if (!hasPositions) return null;

            var positions = ReadVec3Array(root, posIdx, buffers);

            // Normals
            Vector3[] normals = null;
            if (prim.attributes.TryGetValue("NORMAL", out int normIdx))
                normals = ReadVec3Array(root, normIdx, buffers);

            // UVs
            Vector2[] uvs = null;
            if (prim.attributes.TryGetValue("TEXCOORD_0", out int uvIdx))
                uvs = ReadVec2Array(root, uvIdx, buffers);

            // Colors
            Color[] colors = null;
            if (prim.attributes.TryGetValue("COLOR_0", out int colIdx))
                colors = ReadColorArray(root, colIdx, buffers);

            // Joints and weights for skinning
            Vector4[] joints = null;
            Vector4[] weights = null;
            if (prim.attributes.TryGetValue("JOINTS_0", out int jointIdx))
                joints = ReadJointArray(root, jointIdx, buffers);
            if (prim.attributes.TryGetValue("WEIGHTS_0", out int weightIdx))
                weights = ReadVec4Array(root, weightIdx, buffers);

            // Indices
            int[] indices;
            if (prim.indices >= 0)
                indices = ReadIntArray(root, prim.indices, buffers);
            else
                indices = Enumerable.Range(0, positions.Length).ToArray();

            // Apply to mesh
            mesh.SetVertices(positions);
            if (normals != null && normals.Length == positions.Length)
                mesh.SetNormals(normals);
            if (uvs != null && uvs.Length == positions.Length)
                mesh.SetUVs(0, uvs);
            if (colors != null && colors.Length == positions.Length)
                mesh.SetColors(colors);

            mesh.SetIndices(indices, MeshTopology.Triangles, 0);

            if (joints != null || weights != null)
            {
                var boneWeights = new BoneWeight[positions.Length];
                for (int i = 0; i < positions.Length; i++)
                {
                    if (joints != null && i < joints.Length)
                    {
                        boneWeights[i].boneIndex0 = Mathf.RoundToInt(joints[i].x);
                        boneWeights[i].boneIndex1 = Mathf.RoundToInt(joints[i].y);
                        boneWeights[i].boneIndex2 = Mathf.RoundToInt(joints[i].z);
                        boneWeights[i].boneIndex3 = Mathf.RoundToInt(joints[i].w);
                    }
                    if (weights != null && i < weights.Length)
                    {
                        boneWeights[i].weight0 = weights[i].x;
                        boneWeights[i].weight1 = weights[i].y;
                        boneWeights[i].weight2 = weights[i].z;
                        boneWeights[i].weight3 = weights[i].w;
                    }
                }
                mesh.boneWeights = boneWeights;
            }

            mesh.RecalculateBounds();
            return mesh;
        }

        // ── Skin binding ───────────────────────────────────────────────

        static void BuildSkin(GltfRoot root, int skinIdx, GameObject[] nodeGOs, int rootNodeIdx, byte[][] buffers)
        {
            var skin = root.skins[skinIdx];
            if (skin.joints == null || skin.joints.Length == 0) return;

            Matrix4x4[] inverseBindMatrices = null;
            if (skin.inverseBindMatrices >= 0)
                inverseBindMatrices = ReadMatrixArray(root, skin.inverseBindMatrices, buffers);

            // Find all MeshRenderer descendants of this node and bind them
            var rootGO = nodeGOs[rootNodeIdx];
            var renderers = rootGO.GetComponentsInChildren<MeshRenderer>();

            var boneGOs = new Transform[skin.joints.Length];
            for (int i = 0; i < skin.joints.Length; i++)
            {
                int jointNodeIdx = skin.joints[i];
                if (jointNodeIdx >= 0 && jointNodeIdx < nodeGOs.Length)
                    boneGOs[i] = nodeGOs[jointNodeIdx].transform;
            }

            // Calculate bind poses
            var bindPoses = new Matrix4x4[skin.joints.Length];
            for (int i = 0; i < skin.joints.Length; i++)
            {
                if (inverseBindMatrices != null && i < inverseBindMatrices.Length)
                    bindPoses[i] = inverseBindMatrices[i];
                else
                    bindPoses[i] = Matrix4x4.identity;
            }

            foreach (var renderer in renderers)
            {
                if (renderer is SkinnedMeshRenderer)
                    continue; // Already handled

                // For regular MeshRenderer with bone weights, convert to SkinnedMeshRenderer
                var mf = renderer.GetComponent<MeshFilter>();
                if (mf == null || mf.mesh == null || mf.mesh.boneWeights == null || mf.mesh.boneWeights.Length == 0)
                    continue;

                var mesh = mf.mesh;
                var mat = renderer.material;
                var name = renderer.name;

                Destroy(renderer);
                Destroy(mf);

                var smr = renderer.gameObject.AddComponent<SkinnedMeshRenderer>();
                smr.sharedMesh = mesh;
                smr.material = mat;
                smr.bones = boneGOs;
                smr.sharedMesh.bindposes = bindPoses;
                smr.rootBone = boneGOs.Length > 0 ? boneGOs[0] : rootGO.transform;
                smr.updateWhenOffscreen = true;
            }
        }

        // ── Material building ──────────────────────────────────────────

        static UnityEngine.Material BuildMaterial(Material gltfMat)
        {
            var mat = new UnityEngine.Material(Shader.Find("Standard"));

            if (gltfMat.pbrMetallicRoughness != null)
            {
                var pbr = gltfMat.pbrMetallicRoughness;
                if (pbr.baseColorFactor != null && pbr.baseColorFactor.Length >= 4)
                {
                    mat.color = new Color(pbr.baseColorFactor[0], pbr.baseColorFactor[1], pbr.baseColorFactor[2], pbr.baseColorFactor[3]);
                }
                mat.SetFloat("_Metallic", pbr.metallicFactor);
                mat.SetFloat("_Glossiness", 1f - pbr.roughnessFactor);
            }

            if (gltfMat.doubleSided)
            {
                // Standard shader doesn't expose double-sided; enable via script workaround
                mat.SetInt("_Cull", 0); // Off
            }

            if (gltfMat.alphaMode == "MASK")
            {
                mat.SetFloat("_Mode", 1); // Cutout
                mat.SetFloat("_Cutoff", gltfMat.alphaCutoff);
                mat.EnableKeyword("_ALPHATEST_ON");
                mat.renderQueue = 2450;
            }
            else if (gltfMat.alphaMode == "BLEND")
            {
                mat.SetFloat("_Mode", 3); // Transparent
                mat.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.One);
                mat.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                mat.EnableKeyword("_ALPHABLEND_ON");
                mat.renderQueue = 3000;
            }

            return mat;
        }

        // ── Accessor data reading ──────────────────────────────────────

        static int GetComponentSize(int componentType)
        {
            return componentType switch
            {
                5120 => 1, // BYTE
                5121 => 1, // UNSIGNED_BYTE
                5122 => 2, // SHORT
                5123 => 2, // UNSIGNED_SHORT
                5125 => 4, // UNSIGNED_INT
                5126 => 4, // FLOAT
                _ => 0
            };
        }

        static int GetComponentCount(string type)
        {
            return type switch
            {
                "SCALAR" => 1,
                "VEC2" => 2,
                "VEC3" => 3,
                "VEC4" => 4,
                "MAT2" => 4,
                "MAT3" => 9,
                "MAT4" => 16,
                _ => 0
            };
        }

        static byte[] ReadAccessorData(GltfRoot root, int accessorIdx, byte[][] buffers)
        {
            var accessor = root.accessors[accessorIdx];
            if (accessor.bufferView < 0 || accessor.bufferView >= root.bufferViews.Length)
                return null;

            var bufferView = root.bufferViews[accessor.bufferView];
            var buffer = buffers[bufferView.buffer];

            int compSize = GetComponentSize(accessor.componentType);
            int compCount = GetComponentCount(accessor.type);
            int stride = bufferView.byteStride > 0 ? bufferView.byteStride : compSize * compCount;
            int totalSize = stride * accessor.count;

            byte[] data = new byte[totalSize];
            int srcOffset = bufferView.byteOffset + accessor.byteOffset;
            Buffer.BlockCopy(buffer, srcOffset, data, 0, totalSize);

            // Handle sparse accessors
            if (accessor.sparse != null)
            {
                ApplySparse(root, accessor, data, buffers);
            }

            return data;
        }

        static void ApplySparse(GltfRoot root, Accessor accessor, byte[] data, byte[][] buffers)
        {
            var sparse = accessor.sparse;
            int compSize = GetComponentSize(accessor.componentType);
            int compCount = GetComponentCount(accessor.type);
            int stride = compSize * compCount;

            // Read sparse indices
            var sparseIdxAccessor = new Accessor
            {
                bufferView = sparse.indices.bufferView,
                componentType = sparse.indices.componentType,
                count = sparse.count,
                type = "SCALAR",
                byteOffset = sparse.indices.byteOffset
            };
            var idxData = ReadSparseIndices(root, sparseIdxAccessor, buffers);

            // Read sparse values
            var sparseValAccessor = new Accessor
            {
                bufferView = sparse.values.bufferView,
                componentType = accessor.componentType,
                count = sparse.count,
                type = accessor.type,
                byteOffset = sparse.values.byteOffset
            };
            var valData = ReadAccessorDataDirect(root, sparseValAccessor, buffers);

            // Apply sparse overrides
            for (int i = 0; i < sparse.count; i++)
            {
                int targetIdx = idxData[i];
                if (targetIdx >= 0 && targetIdx < accessor.count)
                {
                    Buffer.BlockCopy(valData, i * stride, data, targetIdx * stride, stride);
                }
            }
        }

        static int[] ReadSparseIndices(GltfRoot root, Accessor sparseAcc, byte[][] buffers)
        {
            var bufferView = root.bufferViews[sparseAcc.bufferView];
            var buffer = buffers[bufferView.buffer];
            int compSize = GetComponentSize(sparseAcc.componentType);
            int[] result = new int[sparseAcc.count];
            int offset = bufferView.byteOffset + sparseAcc.byteOffset;
            for (int i = 0; i < sparseAcc.count; i++)
            {
                result[i] = compSize switch
                {
                    2 => BitConverter.ToUInt16(buffer, offset + i * 2),
                    4 => (int)ToUInt32(buffer, offset + i * 4),
                    _ => 0
                };
            }
            return result;
        }

        static byte[] ReadAccessorDataDirect(GltfRoot root, Accessor acc, byte[][] buffers)
        {
            var bufferView = root.bufferViews[acc.bufferView];
            var buffer = buffers[bufferView.buffer];
            int compSize = GetComponentSize(acc.componentType);
            int compCount = GetComponentCount(acc.type);
            int stride = bufferView.byteStride > 0 ? bufferView.byteStride : compSize * compCount;
            int totalSize = stride * acc.count;
            byte[] data = new byte[totalSize];
            int srcOffset = bufferView.byteOffset + acc.byteOffset;
            Buffer.BlockCopy(buffer, srcOffset, data, 0, totalSize);
            return data;
        }

        static Vector2[] ReadVec2Array(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int compSize = GetComponentSize(acc.componentType);
            int stride = compSize * 2;
            var result = new Vector2[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                if (acc.componentType == 5126) // FLOAT
                {
                    result[i].x = ToSingle(data, i * stride);
                    result[i].y = ToSingle(data, i * stride + 4);
                }
                else if (acc.componentType == 5121) // UNSIGNED_BYTE normalized
                {
                    result[i].x = data[i * stride] / 255f;
                    result[i].y = data[i * stride + 1] / 255f;
                }
                else if (acc.componentType == 5123) // UNSIGNED_SHORT normalized
                {
                    result[i].x = ToUInt16(data, i * stride) / 65535f;
                    result[i].y = ToUInt16(data, i * stride + 2) / 65535f;
                }
            }
            return result;
        }

        static Vector3[] ReadVec3Array(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int compSize = GetComponentSize(acc.componentType);
            int stride = compSize * 3;
            var result = new Vector3[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                if (acc.componentType == 5126)
                {
                    result[i].x = ToSingle(data, i * stride);
                    result[i].y = ToSingle(data, i * stride + 4);
                    result[i].z = ToSingle(data, i * stride + 8);
                }
            }
            return result;
        }

        static Vector4[] ReadVec4Array(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int compSize = GetComponentSize(acc.componentType);
            int stride = compSize * 4;
            var result = new Vector4[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                if (acc.componentType == 5126)
                {
                    result[i].x = ToSingle(data, i * stride);
                    result[i].y = ToSingle(data, i * stride + 4);
                    result[i].z = ToSingle(data, i * stride + 8);
                    result[i].w = ToSingle(data, i * stride + 12);
                }
            }
            return result;
        }

        static Vector4[] ReadJointArray(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int compSize = GetComponentSize(acc.componentType);
            int stride = compSize * 4;
            var result = new Vector4[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                if (acc.componentType == 5121) // UNSIGNED_BYTE
                {
                    result[i].x = data[i * stride];
                    result[i].y = data[i * stride + 1];
                    result[i].z = data[i * stride + 2];
                    result[i].w = data[i * stride + 3];
                }
                else if (acc.componentType == 5123) // UNSIGNED_SHORT
                {
                    result[i].x = ToUInt16(data, i * stride);
                    result[i].y = ToUInt16(data, i * stride + 2);
                    result[i].z = ToUInt16(data, i * stride + 4);
                    result[i].w = ToUInt16(data, i * stride + 6);
                }
            }
            return result;
        }

        static Color[] ReadColorArray(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int compSize = GetComponentSize(acc.componentType);
            int compCount = GetComponentCount(acc.type);
            int stride = compSize * compCount;
            var result = new Color[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                if (acc.componentType == 5126)
                {
                    result[i].r = compCount > 0 ? ToSingle(data, i * stride) : 1f;
                    result[i].g = compCount > 1 ? ToSingle(data, i * stride + 4) : 1f;
                    result[i].b = compCount > 2 ? ToSingle(data, i * stride + 8) : 1f;
                    result[i].a = compCount > 3 ? ToSingle(data, i * stride + 12) : 1f;
                }
                else if (acc.componentType == 5121) // UNSIGNED_BYTE normalized
                {
                    result[i].r = compCount > 0 ? data[i * stride] / 255f : 1f;
                    result[i].g = compCount > 1 ? data[i * stride + 1] / 255f : 1f;
                    result[i].b = compCount > 2 ? data[i * stride + 2] / 255f : 1f;
                    result[i].a = compCount > 3 ? data[i * stride + 3] / 255f : 1f;
                }
                else if (acc.componentType == 5123) // UNSIGNED_SHORT normalized
                {
                    result[i].r = compCount > 0 ? ToUInt16(data, i * stride) / 65535f : 1f;
                    result[i].g = compCount > 1 ? ToUInt16(data, i * stride + 2) / 65535f : 1f;
                    result[i].b = compCount > 2 ? ToUInt16(data, i * stride + 4) / 65535f : 1f;
                    result[i].a = compCount > 3 ? ToUInt16(data, i * stride + 6) / 65535f : 1f;
                }
            }
            return result;
        }

        static int[] ReadIntArray(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int compSize = GetComponentSize(acc.componentType);
            int stride = compSize;
            var result = new int[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                result[i] = acc.componentType switch
                {
                    5121 => data[i],
                    5123 => ToUInt16(data, i * stride),
                    5125 => (int)ToUInt32(data, i * stride),
                    _ => 0
                };
            }
            return result;
        }

        static Matrix4x4[] ReadMatrixArray(GltfRoot root, int idx, byte[][] buffers)
        {
            var data = ReadAccessorData(root, idx, buffers);
            if (data == null) return null;
            var acc = root.accessors[idx];
            int stride = 16 * 4; // MAT4 = 16 floats
            var result = new Matrix4x4[acc.count];
            for (int i = 0; i < acc.count; i++)
            {
                var m = new Matrix4x4();
                for (int r = 0; r < 16; r++)
                    m[r] = ToSingle(data, i * stride + r * 4);
                result[i] = m;
            }
            return result;
        }

        // ── Byte helpers ───────────────────────────────────────────────

        static uint ToUInt32(byte[] data, int offset)
        {
            return BitConverter.ToUInt32(data, offset);
        }

        static ushort ToUInt16(byte[] data, int offset)
        {
            return BitConverter.ToUInt16(data, offset);
        }

        static float ToSingle(byte[] data, int offset)
        {
            return BitConverter.ToSingle(data, offset);
        }
    }
}

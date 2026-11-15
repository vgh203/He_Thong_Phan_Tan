"""
lkh_tree.py
Logical Key Hierarchy (LKH) Binary Tree Implementation for Dynamic Group Rekeying.
Implements balanced binary tree (d=2, N=8 members, height h=3).
Supports JOIN (Forward Secrecy, h encrypted blocks) and LEAVE (Backward Secrecy, d*h encrypted blocks).
"""

from typing import Dict, List, Optional, Tuple, Any
import json
from crypto_utils import (
    generate_key_256,
    encrypt_aes_gcm,
    decrypt_aes_gcm,
    key_to_hex,
    hex_to_key,
    format_key_short
)

class LKHNode:
    """Represents a node in the Logical Key Hierarchy binary tree."""
    def __init__(self, node_id: int, level: int, parent_id: Optional[int] = None):
        self.node_id: int = node_id
        self.level: int = level          # 0 = root, 1, 2, 3 = leaf
        self.parent_id: Optional[int] = parent_id
        self.left_child_id: Optional[int] = None
        self.right_child_id: Optional[int] = None
        self.key: bytes = generate_key_256()  # 256-bit AES key
        self.client_id: Optional[str] = None  # Populated if this is a leaf node
        self.is_active: bool = False          # True if occupied by an active member (for leaves) or subtree has active members

    @property
    def is_leaf(self) -> bool:
        return self.left_child_id is None and self.right_child_id is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "level": self.level,
            "parent_id": self.parent_id,
            "left_child_id": self.left_child_id,
            "right_child_id": self.right_child_id,
            "key_short": format_key_short(self.key),
            "key_hex": key_to_hex(self.key),
            "client_id": self.client_id,
            "is_active": self.is_active,
            "is_leaf": self.is_leaf
        }

class LKHTree:
    """
    Full binary tree for LKH with degree d=2, N=8 leaves, height h=3.
    Node IDs use standard 1-based binary heap indexing:
      - Root: 1 (Level 0) -> Root Group Key K_0
      - Level 1: 2, 3
      - Level 2: 4, 5, 6, 7
      - Level 3 (Leaves): 8, 9, 10, 11, 12, 13, 14, 15
        Node 8  -> CLIENT_1
        Node 9  -> CLIENT_2
        Node 10 -> CLIENT_3
        Node 11 -> CLIENT_4
        Node 12 -> CLIENT_5
        Node 13 -> CLIENT_6
        Node 14 -> CLIENT_7
        Node 15 -> CLIENT_8
    """
    def __init__(self, num_members: int = 8):
        self.n_members: int = num_members
        self.height: int = 3  # log2(8) = 3
        self.degree: int = 2
        self.nodes: Dict[int, LKHNode] = {}
        self.client_to_leaf: Dict[str, int] = {}
        self.leaf_to_client: Dict[int, str] = {}
        self._build_tree()

    def _build_tree(self):
        """Construct a complete binary tree with 15 nodes (1 root, 6 internal, 8 leaves)."""
        # Root is node 1 at level 0
        self.nodes[1] = LKHNode(node_id=1, level=0, parent_id=None)
        self.nodes[1].is_active = True

        # Internal nodes at level 1 (nodes 2, 3) and level 2 (nodes 4, 5, 6, 7)
        for nid in range(1, 8):
            left_id = 2 * nid
            right_id = 2 * nid + 1
            self.nodes[nid].left_child_id = left_id
            self.nodes[nid].right_child_id = right_id

            left_level = self.nodes[nid].level + 1
            right_level = left_level

            self.nodes[left_id] = LKHNode(node_id=left_id, level=left_level, parent_id=nid)
            self.nodes[right_id] = LKHNode(node_id=right_id, level=right_level, parent_id=nid)

        # Mapping for 8 client leaves: Node 8..15 -> CLIENT_1..CLIENT_8
        for i in range(1, self.n_members + 1):
            leaf_id = 7 + i  # 8..15
            client_id = f"CLIENT_{i}"
            self.nodes[leaf_id].client_id = client_id
            self.client_to_leaf[client_id] = leaf_id
            self.leaf_to_client[leaf_id] = client_id
            # Initially, active state is False until client actually joins/activates
            self.nodes[leaf_id].is_active = False

    @property
    def root_key(self) -> bytes:
        """Current Root Group Key K_0."""
        return self.nodes[1].key

    def get_path_to_root(self, node_id: int) -> List[int]:
        """
        Returns the list of node IDs from node_id up to root (inclusive).
        Length for a leaf is h + 1 = 4.
        """
        path = []
        curr = node_id
        while curr is not None:
            path.append(curr)
            curr = self.nodes[curr].parent_id
        return path

    def get_keys_for_client(self, client_id: str) -> Dict[int, bytes]:
        """Return a mapping of node_id -> key_bytes for all nodes on client's path."""
        if client_id not in self.client_to_leaf:
            raise ValueError(f"Unknown client: {client_id}")
        leaf_id = self.client_to_leaf[client_id]
        path = self.get_path_to_root(leaf_id)
        return {nid: self.nodes[nid].key for nid in path}

    def register_initial_member(self, client_id: str) -> Dict[int, bytes]:
        """
        Activates an initial member without rekeying (used during setup/bootstrap).
        Returns the initial key dictionary for the member.
        """
        if client_id not in self.client_to_leaf:
            raise ValueError(f"Client {client_id} has no assigned leaf slot.")
        leaf_id = self.client_to_leaf[client_id]
        self.nodes[leaf_id].is_active = True
        return self.get_keys_for_client(client_id)

    def handle_join(self, client_id: str) -> Tuple[Dict[str, Any], Dict[int, bytes]]:
        """
        Handles dynamic JOIN for client_id (Forward Secrecy).
        Steps:
          1. Mark client leaf as active.
          2. Path from leaf to root contains h=3 ancestor nodes (parent, ancestor, root).
          3. Generate new keys for all ancestor nodes on the path:
             - Node parent (Level 2)
             - Node ancestor (Level 1)
             - Node root (Level 0)
          4. For each ancestor node v, encrypt K_v_new using old key K_v_old:
             Rekey block: {node_id: v, encrypt_by: v, nonce: hex, ciphertext: hex}
             Total: h = 3 encrypted blocks.
          5. Existing members holding K_v_old can decrypt K_v_new.
             The new member CLIENT receives its fresh path keys directly.
        Returns:
          - rekey_message: dict format ready for multicast broadcast to existing members
          - client_key_bundle: dict of {node_id: key_bytes} for the new client
        """
        if client_id not in self.client_to_leaf:
            raise ValueError(f"Unknown client {client_id}")

        leaf_id = self.client_to_leaf[client_id]
        self.nodes[leaf_id].is_active = True

        # Ancestors on path from leaf to root (excluding the leaf itself)
        ancestor_ids = self.get_path_to_root(leaf_id)[1:]  # e.g., [5, 2, 1] for leaf 10
        # Order from parent up to root
        rekey_blocks: List[Dict[str, Any]] = []

        old_keys = {nid: self.nodes[nid].key for nid in ancestor_ids}
        new_keys = {nid: generate_key_256() for nid in ancestor_ids}

        # For each ancestor node, encrypt new key with old key
        for nid in ancestor_ids:
            old_k = old_keys[nid]
            new_k = new_keys[nid]
            nonce, ct = encrypt_aes_gcm(old_k, new_k)
            rekey_blocks.append({
                "target_node_id": nid,
                "encrypting_node_id": nid,
                "nonce": nonce.hex(),
                "ciphertext": ct.hex()
            })
            # Update key in tree
            self.nodes[nid].key = new_k

        # Total encrypted blocks is exactly h = 3
        rekey_message = {
            "msg_type": "JOIN",
            "client_id": client_id,
            "rekey_node_id": leaf_id,
            "blocks_count": len(rekey_blocks),
            "rekey_blocks": rekey_blocks
        }

        # The new client receives its own leaf key and the newly updated ancestor keys
        client_key_bundle = {leaf_id: self.nodes[leaf_id].key}
        for nid in ancestor_ids:
            client_key_bundle[nid] = self.nodes[nid].key

        return rekey_message, client_key_bundle

    def handle_leave(self, client_id: str) -> Dict[str, Any]:
        """
        Handles dynamic LEAVE for client_id (Backward Secrecy).
        Steps:
          1. Mark client leaf as inactive (revoked).
          2. Path from leaf to root contains h=3 ancestor nodes (Level 2, Level 1, Level 0).
          3. All keys along this path are compromised and must be revoked & refreshed.
          4. At each ancestor level on the path from bottom up:
             Server generates new key K_v_new.
             Because leaving client knows K_v_old, server CANNOT encrypt K_v_new with K_v_old.
             Instead, at each level, K_v_new is encrypted using the keys of each child:
             - At Level 2 (Parent of leaving node):
                 Children are leaving leaf and sibling leaf.
                 Sibling is active; Server encrypts K_parent_new using K_sibling.
                 To form d*h = 2*3 = 6 blocks, we generate 2 blocks per ancestor level:
                 - For sibling child: Encrypted with active sibling key.
                 - For leaving child: Explicit revocation placeholder block or encrypted under revoked key dummy.
             - At Level 1:
                 Children are Left Child and Right Child.
                 One child subtree was rekeyed; the other child subtree is untouched.
                 Server encrypts K_ancestor_new with Left Child key and with Right Child key.
                 (2 blocks).
             - At Level 0 (Root):
                 Children are Left Child (Node 2) and Right Child (Node 3).
                 Server encrypts K_root_new with Node 2 key and Node 3 key.
                 (2 blocks).
             Total: d * h = 2 * 3 = 6 rekey blocks!
        Returns:
          - rekey_message: dict format ready for multicast broadcast to remaining members
        """
        if client_id not in self.client_to_leaf:
            raise ValueError(f"Unknown client {client_id}")

        leaf_id = self.client_to_leaf[client_id]
        self.nodes[leaf_id].is_active = False

        # Ancestors from parent to root
        ancestor_ids = self.get_path_to_root(leaf_id)[1:]  # e.g., [7, 3, 1] for leaf 14
        rekey_blocks: List[Dict[str, Any]] = []

        # We proceed level by level from bottom (parent) to top (root)
        current_child_on_path = leaf_id

        for nid in ancestor_ids:
            node = self.nodes[nid]
            new_key = generate_key_256()

            left_child_id = node.left_child_id
            right_child_id = node.right_child_id

            # Process both children (d=2)
            for child_id in [left_child_id, right_child_id]:
                if child_id == current_child_on_path and child_id == leaf_id:
                    # This is the leaving client's leaf! It is revoked!
                    # We do NOT encrypt the valid new key with the leaving client's key.
                    # We produce a revocation token block so client_7 cannot decrypt it.
                    revocation_dummy = b"REVOKED_SLOT_ACCESS_TERMINATED"
                    nonce, ct = encrypt_aes_gcm(self.nodes[child_id].key, revocation_dummy)
                    rekey_blocks.append({
                        "target_node_id": nid,
                        "encrypting_node_id": child_id,
                        "is_revoked_target": True,
                        "nonce": nonce.hex(),
                        "ciphertext": ct.hex()
                    })
                else:
                    # Legitimate branch: encrypt new key with child_id's current key
                    child_key = self.nodes[child_id].key
                    nonce, ct = encrypt_aes_gcm(child_key, new_key)
                    rekey_blocks.append({
                        "target_node_id": nid,
                        "encrypting_node_id": child_id,
                        "is_revoked_target": False,
                        "nonce": nonce.hex(),
                        "ciphertext": ct.hex()
                    })

            # Commit new key to this ancestor node
            self.nodes[nid].key = new_key
            # Move up the path
            current_child_on_path = nid

        rekey_message = {
            "msg_type": "LEAVE",
            "revoked_client_id": client_id,
            "rekey_node_id": leaf_id,
            "blocks_count": len(rekey_blocks),  # exactly 6
            "d_factor": self.degree,
            "h_factor": self.height,
            "rekey_blocks": rekey_blocks
        }

        return rekey_message

    def get_tree_state(self) -> Dict[str, Any]:
        """Export tree state for dashboard visualization."""
        return {
            "height": self.height,
            "degree": self.degree,
            "total_nodes": len(self.nodes),
            "root_key_short": format_key_short(self.root_key),
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "active_members": [cid for cid, lid in self.client_to_leaf.items() if self.nodes[lid].is_active]
        }


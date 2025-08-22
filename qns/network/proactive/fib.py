#    Multiverse Quantum Network Simulator: a simulator for comparative
#    evaluation of quantum routing strategies
#    Copyright (C) [2025] Amar Abane
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

from collections.abc import Set
from typing import TypedDict

try:
    from typing import Unpack
except ImportError:
    from typing_extensions import Unpack


class FIBEntry(TypedDict):
    path_id: int
    request_id: int
    path_vector: list[str]
    swap_sequence: list[int]
    purification_scheme: dict[str, int]


def find_index_and_swapping_rank(fib_entry: FIBEntry, node_name: str) -> tuple[int, int]:
    """
    Determine the swapping rank of a node.

    Args:
        fib_entry: a FIB entry.
        node_name: a node name that exists in path_vector.

    Returns:
        [0]: The node index in the route.
        [1]: A nonnegative integer that represents swapping rank of the node.
             A node with smaller rank shall perform swapping before a node with larger rank.

    Raises:
        IndexError - node does not exist in path_vector.
    """
    idx = fib_entry["path_vector"].index(node_name)
    return idx, fib_entry["swap_sequence"][idx]


def is_swap_disabled(fib_entry: FIBEntry) -> bool:
    """
    Determine whether swapping has been disabled.

    To disable swapping, set swap_sequence to a list of zeros.

    When swapping is disabled, the forwarder will consume entanglement upon completing purification,
    without attempting entanglement swapping.

    Args:
        fib_entry: a FIB entry.
    """
    swap = fib_entry["swap_sequence"]
    return swap[0] == 0 == swap[-1]


class ForwardingInformationBase:
    def __init__(self):
        self.table: dict[int, FIBEntry] = {}
        """
        FIB table.
        Key is path_id.
        Value is FIB entry.
        """
        self.req_path_map: dict[int, set[int]] = {}
        """
        Lookup table indexed by request_id.
        Key is request_id.
        Value is path_id set.
        """

    def get(self, path_id: int) -> FIBEntry:
        """
        Retrieve an entry by path_id.

        Raises:
            IndexError - Entry not found.
        """
        try:
            return self.table[path_id]
        except KeyError:
            raise IndexError(f"FIB entry not found for path_id={path_id}")

    def insert_or_replace(self, **entry: Unpack[FIBEntry]):
        """
        Insert an entry or replace entry with same path_id.
        """
        path_id = entry["path_id"]
        self.erase(path_id)
        self.table[path_id] = entry

        request_id = entry["request_id"]
        paths = self.req_path_map.setdefault(request_id, set())
        paths.add(path_id)

    def erase(self, path_id: int):
        """
        Remove an entry from the table.

        Nonexistent entry is silent ignored.
        """
        try:
            entry = self.table.pop(path_id)
        except KeyError:
            return

        request_id = entry["request_id"]
        paths = self.req_path_map[request_id]
        paths.remove(path_id)
        if not paths:
            del self.req_path_map[request_id]

    def list_path_ids_by_request_id(self, request_id: int) -> Set[int]:
        return self.req_path_map.get(request_id, set())

    def __repr__(self):
        """Return a string representation of the forwarding table."""
        return "\n".join(
            f"Path ID: {path_id}, Request ID: {entry['request_id']}, Path: {entry['path_vector']}, "
            f"Swap Sequence: {entry['swap_sequence']}, "
            f"Purification: {entry['purification_scheme']}"
            for path_id, entry in self.table.items()
        )

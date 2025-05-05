#    SimQN: a discrete-event simulator for the quantum networks
#    Copyright (C) 2021-2022 Amar Abane
#    National Institute of Standards and Technology, NIST.
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

from typing import Dict, Optional, List
import uuid

from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket, RecvClassicPacket
from qns.entity.memory.memory import QuantumMemory
from qns.entity.memory.memory_qubit import MemoryQubit
from qns.entity.node.app import Application
from qns.entity.node.node import Node
from qns.entity.node.qnode import QNode
from qns.entity.node.controller import Controller
from qns.entity.qchannel.qchannel import QuantumChannel, RecvQubitPacket
from qns.models.core.backend import QuantumModel
from qns.network.requests import Request
from qns.simulator.event import Event, func_to_event
from qns.simulator.simulator import Simulator
from qns.network import QuantumNetwork
from qns.models.epr import WernerStateEntanglement
from qns.simulator.ts import Time
import qns.utils.log as log
from qns.network.protocol.fib import ForwardingInformationBase
from qns.network import QuantumNetwork, TimingModeEnum, SignalTypeEnum

import copy

class ProactiveRouting(Application):
    """
    ProactiveRouting runs at the network layer of QNodes (routers) and receives instructions from the controller
    It implements the forwarding phase (i.e., entanglement generation and swapping) while the routing is done at the controller. 
    Purification will be in a sepeare process/module.
    """
    def __init__(self, ps: float = 1.0):
        super().__init__()

        self.ps = ps
        self.sync_current_phase = SignalTypeEnum.INTERNAL

        self.net: QuantumNetwork = None
        self.own: QNode = None
        self.memories: QuantumMemory = None
        
        self.fib: ForwardingInformationBase = ForwardingInformationBase()
        self.link_layer = None

        self.waiting_qubits = []        # stores the qubits waiting for the INTERNAL phase (SYNC mode)

        # so far we can only distinguish between classic and qubit events (not source Entity)
        self.add_handler(self.RecvClassicPacketHandler, [RecvClassicPacket])
        
        self.parallel_swappings = {}
        
        self.e2e_count = 0

    def install(self, node: QNode, simulator: Simulator):
        from qns.network.protocol.link_layer import LinkLayer
        super().install(node, simulator)
        self.own: QNode = self._node
        self.memories: List[QuantumMemory] = self.own.memories
        self.net = self.own.network
        ll_apps = self.own.get_apps(LinkLayer)
        if ll_apps:
            self.link_layer = ll_apps[0]
        else:
            raise Exception("No LinkLayer protocol found")

    def RecvClassicPacketHandler(self, node: Node, event: Event):
        # node is the local node of this app
        if isinstance(event.packet.src, Controller):
            self.handle_control(event)
        elif isinstance(event.packet.src, QNode):
            self.handle_signaling(event)
        else:
            log.warn(f"Unexpected event from entity type: {type(event.packet.src)}")

    # handle forwarding instructions from the controller
    def handle_control(self, packet: RecvClassicPacket):
        msg = packet.packet.get()
        log.debug(f"{self.own.name}: routing instructions: {msg}")

        path_id = msg['path_id']
        instructions = msg['instructions']
        # TODO: verify vectors consistency (size, min/max, etc.)

        prev_neighbor = None
        next_neighbor = None
        pn = ""
        nn = ""
        # node gets prev and next node from route vector:
        if self.own.name in instructions['route']:
            i = instructions['route'].index(self.own.name)
            pn, nn = (instructions['route'][i - 1] if i > 0 else None, instructions['route'][i + 1] if i < len(instructions['route']) - 1 else None)
        else:
            raise Exception(f"Node {self.own.name} not found in route vector {instructions['route']}")

        # use prev and next node to get corresponding channels
        # use channel names to get corresponding memories
        prev_qchannel = None
        prev_qmem = None
        if pn:
            prev_neighbor = self.net.get_node(pn)
            prev_qchannel: QuantumChannel = self.own.get_qchannel(prev_neighbor)
            if prev_qchannel:
                prev_qmem = next(qmem for qmem in self.memories if qmem.name == prev_qchannel.name)
            else:
                raise Exception(f"Qchannel not found for neighbor {prev_neighbor}")

        next_qchannel = None
        next_qmem = None
        if nn:
            next_neighbor = self.own.network.get_node(nn)
            next_qchannel: QuantumChannel = self.own.get_qchannel(next_neighbor)
            if next_qchannel:
                next_qmem = next(qmem for qmem in self.memories if qmem.name == next_qchannel.name)
            else:
                raise Exception(f"Qchannel not found for neighbor {next_neighbor}")

        # use mux info to allocate qubits in each memory, keep qubit addresses
        prev_qubits = []
        next_qubits = []
        if instructions['mux'] == "B":
            if instructions["m_v"]:
                log.debug(f"{self.own}: Allocating qubits for buffer-space mux")
                num_prev, num_next = self.compute_qubit_allocation(instructions['route'], instructions['m_v'], self.own.name)
                if num_prev and prev_qmem:
                    if num_prev >= prev_qmem.free:
                        for i in range(num_prev): prev_qubits.append(prev_qmem.allocate(path_id=path_id))
                    else:
                        raise Exception(f"Not enough qubits left for this allocation.")
                if num_next and next_qmem:
                    if num_next >= next_qmem.free:
                        for i in range(num_next): next_qubits.append(next_qmem.allocate(path_id=path_id))
                    else:
                        raise Exception(f"Not enough qubits left for this allocation.")
            else:
                log.debug(f"{self.own}: Qubits allocation not provided. Allocate all qubits")
                if prev_qmem:
                    if prev_qmem.free == prev_qmem.capacity:
                        for i in range(prev_qmem.free): prev_qubits.append(prev_qmem.allocate(path_id=path_id))
                    else:
                        raise Exception(f"Memory {prev_qmem.name} has allocated qubits and cannot be used with Blocking mux.")
                if next_qmem:
                    if next_qmem.free == next_qmem.capacity:
                        for i in range(next_qmem.free): next_qubits.append(next_qmem.allocate(path_id=path_id))
                    else:
                        raise Exception(f"Memory {next_qmem.name} has allocated qubits and cannot be used with Blocking mux.")
        log.debug(f"allocated qubits: prev={prev_qubits} | next={next_qubits}")

        # populate FIB
        if self.fib.get_entry(path_id):
            self.fib.delete_entry(path_id)        
        self.fib.add_entry(path_id=path_id, path_vector=instructions['route'], swap_sequence=instructions['swap'], 
                           purification_scheme=instructions['purif'], qubit_addresses=[])

        # call LINK LAYER to start generating EPRs on next channels: this will trigger "new_epr" events
        if next_neighbor:
            from qns.network.protocol.event import LinkLayerManageActiveChannels, TypeEnum
            t = self._simulator.tc #+ self._simulator.time(sec=0)   # simulate comm. time between L3 and L2
            ll_request = LinkLayerManageActiveChannels(link_layer=self.link_layer, next_hop=next_neighbor, 
                                                       type=TypeEnum.ADD, t=t, by=self)
            self._simulator.add_event(ll_request)
            # log.debug(f"{self.own.name}: calling link layer to generate eprs for path {path_id} with next hop {next_neighbor}")
        
        # TODO: on remove path:
        # update FIB
        # if qchannel is not used by any path -> notify LinkLayer to stop generating EPRs over it:
        #t = self._simulator.tc + self._simulator.time(sec=1e-6)   # simulate comm. time between L3 and L2
        #ll_request = LinkLayerManageActiveChannels(link_layer=self.link_layer, next_hop=next_hop, 
        #                                           type=TypeEnum.REMOVE, t=t, by=self)
        #self._simulator.add_event(ll_request)


    # handle classical message from neighbors
    def handle_signaling(self, packet: RecvClassicPacket):
        msg = packet.packet.get()
        cchannel = packet.cchannel

        from_node: QNode = cchannel.node_list[0] \
            if cchannel.node_list[1] == self.own else cchannel.node_list[1]

        cmd = msg["cmd"]
        path_id = msg["path_id"]

        if cmd == "SWAP_UPDATE":
            if self.own.timing_mode == TimingModeEnum.SYNC and self.sync_current_phase != SignalTypeEnum.INTERNAL:
                debug.log(f"{self.own}: INT phase is over -> stop swaps")
                return

            fib_entry = self.fib.get_entry(path_id)
            if not fib_entry:
                raise Exception(f"{self.own}: FIB entry not found for path {path_id}")

            route = fib_entry['path_vector']
            swap_sequence = fib_entry['swap_sequence']
            sender_idx = route.index(msg['swapping_node'])
            sender_rank = swap_sequence[sender_idx]
            own_idx = route.index(self.own.name)
            own_rank = swap_sequence[own_idx]

            # destination means:
            # - the node needs to update its local qubit wrt a remote node (partner)
            # - this etg **side** becomes ready to purify/swap
            if msg["destination"] == self.own.name:
                if own_rank > sender_rank:       # this node didn't swap for sure 
                    qmem, qubit = self.get_memory_qubit(msg["epr"])
                    if qmem:
                        # swap failed or oldest pair decohered -> release qubit 
                        if msg["new_epr"] is None or msg["new_epr"].decoherence_time <= self._simulator.tc:
                            qmem.read(key=qubit.addr)
                            qubit.fsm.to_release()
                            from qns.network.protocol.event import QubitReleasedEvent
                            event = QubitReleasedEvent(link_layer=self.link_layer, qubit=qubit, t=self._simulator.tc, by=qmem)
                            self._simulator.add_event(event)
                        else:    # update old EPR with new EPR (fidelity and partner)
                            updated = qmem.update(old_qm=msg["epr"], new_qm=msg["new_epr"])
                            if not updated:
                                log.debug(f"### {self.own}: VERIFY -> EPR update {updated}")
                            if updated and self.eval_swapping_conditions(fib_entry, msg["partner"]):
                                # log.debug(f"{self.own}: qubit {qubit} go to purif")
                                qubit.fsm.to_purif()
                                self.purif(qmem, qubit, fib_entry, msg["partner"])
                    else:      # epr decohered -> release qubit
                        log.debug(f"{self.own}: EPR {msg['epr']} decohered during SU transmissions")
                elif own_rank == sender_rank:     # the two nodes may have swapped
                    # log.debug(f"### {self.own}: rcvd SU from same-rank node {msg['new_epr']}")
                    qmem, qubit = self.get_memory_qubit(msg["epr"])
                    if qmem:      # there was no parallel swap
                        # clean parallel_swappings
                        self.parallel_swappings.pop(msg["epr"], None)
                        if msg["new_epr"] is None or msg["new_epr"].decoherence_time <= self._simulator.tc:
                            qmem.read(key=qubit.addr)
                            qubit.fsm.to_release()
                            from qns.network.protocol.event import QubitReleasedEvent
                            event = QubitReleasedEvent(link_layer=self.link_layer, qubit=qubit, t=self._simulator.tc, by=qmem)
                            self._simulator.add_event(event)
                        else:    # update old EPR with new EPR (fidelity and partner)
                            updated = qmem.update(old_qm=msg["epr"], new_qm=msg["new_epr"])
                            if not updated:
                                log.debug(f"### {self.own}: VERIFY -> EPR update {updated}")
                    else:
                        if msg["epr"] in self.parallel_swappings:
                            (shared_epr, other_epr, my_new_epr) = self.parallel_swappings[msg["epr"]]
                            if msg["new_epr"] is None or msg["new_epr"].decoherence_time <= self._simulator.tc:
                                if other_epr.dst == self.own:
                                    destination = other_epr.src
                                    partner = shared_epr.dst
                                else:
                                    destination = other_epr.dst
                                    partner = shared_epr.src
                                fwd_msg = {
                                    "cmd": "SWAP_UPDATE",
                                    "path_id": msg['path_id'],
                                    "swapping_node": msg['swapping_node'],
                                    "partner": partner.name,
                                    "epr": my_new_epr.name,
                                    "new_epr": None,
                                    "destination": destination.name,
                                    "fwd": True
                                }
                                # log.debug(f"{self.own}: FWD SU with delay")
                                self.send_swap_update(dest=destination, msg=fwd_msg, route=fib_entry["path_vector"], delay=True)
                                self.parallel_swappings.pop(msg["epr"], None)
                            else:    # a neighbor successfully swapped in parallel with this node
                                new_epr = msg["new_epr"]    # is the epr from neighbor swap
                                merged_epr = new_epr.swapping(epr=other_epr)    # merge the two swaps (phyisically already happened)
                                if other_epr.dst == self.own:
                                    if merged_epr is not None:
                                        merged_epr.src = other_epr.src
                                        merged_epr.dst = new_epr.dst
                                    partner = new_epr.dst.name
                                    destination = other_epr.src
                                else:
                                    if merged_epr is not None:
                                        merged_epr.src = new_epr.src
                                        merged_epr.dst = other_epr.dst
                                    partner = new_epr.src.name
                                    destination = other_epr.dst
                                fwd_msg = {
                                    "cmd": "SWAP_UPDATE",
                                    "path_id": msg['path_id'],
                                    "swapping_node": msg['swapping_node'],
                                    "partner": partner,
                                    "epr": my_new_epr.name,
                                    "new_epr": merged_epr,
                                    "destination": destination.name,
                                    "fwd": True
                                }
                                # log.debug(f"{self.own}: FWD SU with delay")
                                self.send_swap_update(dest=destination, msg=fwd_msg, route=fib_entry["path_vector"], delay=True)
                                self.parallel_swappings.pop(msg["epr"], None)
                            
                                # update parallel swappings for next potential cases:
                                p_idx = route.index(partner)
                                p_rank = swap_sequence[p_idx]
                                if (own_rank == p_rank) and (merged_epr is not None):
                                    self.parallel_swappings[new_epr.name] = (new_epr, other_epr, merged_epr)
                        else:
                            # pass
                            log.debug(f"### {self.own}: EPR {msg['epr']} decohered after swapping [parallel]")
                else:
                    log.debug(f"### {self.own}: VERIFY -> rcvd SU from higher-rank node")
            else:
                # node is not destination of this SU: forward message
                if own_rank <= sender_rank:
                    msg_copy = copy.deepcopy(msg)
                    log.debug(f"{self.own}: FWD SWAP_UPDATE")
                    msg_copy["fwd"] = True
                    self.send_swap_update(dest=packet.packet.dest, msg=msg_copy, route=fib_entry["path_vector"])
                else:
                    log.debug(f"### {self.own}: VERIFY -> not the swapping dest and did not swap")

    # handle internal events
    def handle_event(self, event: Event) -> None:
        from qns.network.protocol.event import QubitEntangledEvent, EndToEndEntanglementEvent
        if isinstance(event, QubitEntangledEvent):    # this event starts the lifecycle for a qubit
            if self.own.timing_mode == TimingModeEnum.ASYNC or self.own.timing_mode == TimingModeEnum.LSYNC:
                self.handle_entangled_qubit(event)
            else:           # SYNC
                if self.sync_current_phase == SignalTypeEnum.EXTERNAL:
                    # Accept new etg while we are in EXT phase
                    # Assume t_coh > t_ext: QubitEntangledEvent events should correspond to different qubits, no redundancy
                    self.waiting_qubits.append(event)
        """ elif isinstance(event, EndToEndEntanglementEvent):
            qmem, qubit = self.get_memory_qubit(event.epr)
            if qmem:
                qmem.read(address=qubit.addr)
                log.debug(f"{self.own}: consume e2e entanglement")
                from qns.network.protocol.event import QubitReleasedEvent
                qubit.fsm.to_release()
                event = QubitReleasedEvent(link_layer=self.link_layer, qubit=qubit, e2e=True,
                                       t=self._simulator.tc, by=qmem)
                self._simulator.add_event(event) """

    def handle_entangled_qubit(self, event):
        if event.qubit.pid is not None:     # for buffer-space/blocking mux
            fib_entry = self.fib.get_entry(event.qubit.pid)
            if fib_entry:
                if self.eval_swapping_conditions(fib_entry, event.neighbor.name):
                    qchannel: QuantumChannel = self.own.get_qchannel(event.neighbor)
                    if qchannel:
                        event.qubit.fsm.to_purif()
                        qmem = next(qmem for qmem in self.memories if qmem.name == qchannel.name)
                        self.purif(qmem, event.qubit, fib_entry, event.neighbor.name)
                    else:
                        raise Exception(f"No qchannel found for neighbor {event.neighbor.name}")
            else:
                raise Exception(f"No FIB entry found for pid {event.qubit.pid}")
        else:        # for statistical mux
            log.debug("Qubit not allocated to any path. Statistical mux not supported yet.")

    # corresponds more to: eval qubit eligibility
    def eval_swapping_conditions(self, fib_entry: Dict, partner: str) -> bool:
        route = fib_entry['path_vector']
        swap_sequence = fib_entry['swap_sequence']
        partner_idx = route.index(partner)
        partner_rank = swap_sequence[partner_idx]
        own_idx = route.index(self.own.name)
        own_rank = swap_sequence[own_idx]

        # If partner rank is higher or equal -> go to PURIF
        if partner_rank >= own_rank:
            return True
        return False

    def purif(self, qmem: QuantumMemory, qubit: MemoryQubit, fib_entry: Dict, partner: str):
        # Will remove when purif cycle is implemented:
        qubit.fsm.to_eligible()
        self.eligible(qmem, qubit, fib_entry)

        # consume right away:
        """ _, qm = qmem.read(address=qubit.addr)
        qubit.fsm.to_release()
        log.debug(f"{self.own}: consume entanglement: <{qubit.addr}> {qm.src.name} - {qm.dst.name}")
        from qns.network.protocol.event import QubitReleasedEvent
        event = QubitReleasedEvent(link_layer=self.link_layer, qubit=qubit, e2e=self.own.name=='S',
                                   t=self._simulator.tc, by=qmem)
        self._simulator.add_event(event) """

        # TODO:
        # get partner's rank: if strictly higher -> i am init purif
        # To init purif:
        #   - get purif_scheme for the segment (own-partner)
        #   - if num_rounds (or condition) is None/satified: return ELIGIBLE for this qubit
        #   - else: check if available EPRs (same path_id and same partner)
        #           if enough pairs -> enter purif cycle (passive slightly behind active in transitions)
        #           else -> return

    def eligible(self, qmem: QuantumMemory, qubit: MemoryQubit, fib_entry: Dict):
        if self.own.timing_mode == TimingModeEnum.SYNC and self.sync_current_phase != SignalTypeEnum.INTERNAL:
            debug.log(f"{self.own}: INT phase is over -> stop swaps")
            return

        swap_sequence = fib_entry['swap_sequence']
        route = fib_entry['path_vector']
        own_idx = route.index(self.own.name)
        if own_idx > 0 and own_idx < len(route)-1:     # intermediate node
            (other_qmem, qubits) = self.check_eligible_qubit(qmem, fib_entry['path_id'])   # check if there is another eligible qubit
            if not other_qmem:
                return
            else:     # do swapping
                # check if there are different partners in eligible eprs:
                #src_dst_pairs = {
                #    (epr.src.name, epr.dst.name)
                #    for _, epr in qubits
                #}
                #has_different_src_dst = len(src_dst_pairs) > 1
                #if has_different_src_dst:     
                #    log.debug(f"{self.own}: different partners on eligible qubits -> {has_different_src_dst}")
                #    log.debug(f"{self.own}: {src_dst_pairs}")
                #    import random
                #    other_qubit, other_epr = random.choice(qubits)    # pick up random qubit
                #else:       
                other_qubit, other_epr = qubits[0]     # pick up one qubit  -> TODO: quasi-local

                this_epr = qmem.get(address=qubit.addr)[1]

                # select highest or closet age epr:
                # other_qubit, other_epr = max(qubits, key=lambda pair: pair[1].decoherence_time)
                # other_qubit, other_epr = min(qubits, key=lambda pair: abs(pair[1].decoherence_time - this_epr.decoherence_time))

                # order eprs and prev/next nodes
                if this_epr.dst == self.own:
                    prev_partner = this_epr.src
                    prev_epr = this_epr
                    next_partner = other_epr.dst
                    next_epr = other_epr
                    
                    prev_qubit = qubit
                    next_qubit = other_qubit
                    prev_qmem = qmem
                    next_qmem = other_qmem
                elif this_epr.src == self.own:
                    prev_partner = other_epr.src
                    prev_epr = other_epr
                    next_partner = this_epr.dst
                    next_epr = this_epr
                    
                    prev_qubit = other_qubit
                    next_qubit = qubit
                    prev_qmem = other_qmem
                    next_qmem = qmem
                else:
                    raise Exception(f"Unexpected: swapping EPRs {this_epr} x {other_epr}")

                # if elem epr -> assign ch_index
                if not prev_epr.orig_eprs:
                    prev_epr.ch_index = own_idx - 1
                if not next_epr.orig_eprs:
                    next_epr.ch_index = own_idx

                new_epr = this_epr.swapping(epr=other_epr, ps=self.ps)
                log.debug(f"{self.own}: SWAP {'SUCC' if new_epr else 'FAILED'} | {qmem}.{qubit} x {other_qmem}.{other_qubit}")
                if new_epr:    # swapping succeeded
                    new_epr.src = prev_partner
                    new_epr.dst = next_partner

                    # Keep some info in case of parallel swapping with neighbors:
                    own_rank = swap_sequence[own_idx]
                    prev_p_idx = route.index(prev_partner.name)
                    prev_p_rank = swap_sequence[prev_p_idx]
                    if own_rank == prev_p_rank:
                        # log.debug(f"===> {self.own}: potential parallel swap with prev neighbor {prev_partner.name}")
                        self.parallel_swappings[prev_epr.name] = (prev_epr, next_epr, new_epr)

                    next_p_idx = route.index(next_partner.name)
                    next_p_rank = swap_sequence[next_p_idx]
                    if own_rank == next_p_rank:
                        # log.debug(f"===> {self.own}: potential parallel swap with next neighbor {next_partner.name}")
                        self.parallel_swappings[next_epr.name] = (next_epr, prev_epr, new_epr)

                # send SWAP_UPDATE to both swapping partners:
                prev_partner_msg = {
                    "cmd": "SWAP_UPDATE",
                    "path_id": fib_entry["path_id"],
                    "swapping_node": self.own.name,
                    "partner": next_partner.name,
                    "epr": prev_epr.name,
                    "new_epr": new_epr,        # None means swapping failed
                    "destination": prev_partner.name,
                    "fwd": False
                }
                self.send_swap_update(dest=prev_partner, msg=prev_partner_msg, route=fib_entry["path_vector"])

                next_partner_msg = {
                    "cmd": "SWAP_UPDATE",
                    "path_id": fib_entry["path_id"],
                    "swapping_node": self.own.name,
                    "partner": prev_partner.name,
                    "epr": next_epr.name,
                    "new_epr": new_epr,         # None means swapping failed
                    "destination": next_partner.name,
                    "fwd": False
                }
                self.send_swap_update(dest=next_partner, msg=next_partner_msg, route=fib_entry["path_vector"])

                # release qubits
                qmem.read(address=qubit.addr)
                other_qmem.read(key=other_qubit.addr)
                qubit.fsm.to_release()
                other_qubit.fsm.to_release()
                from qns.network.protocol.event import QubitReleasedEvent
                ev1 = QubitReleasedEvent(link_layer=self.link_layer, qubit=prev_qubit, t=self._simulator.tc, by=prev_qmem)
                ev2 = QubitReleasedEvent(link_layer=self.link_layer, qubit=next_qubit, t=self._simulator.tc + Time(sec=1e-6), by=next_qmem)
                self._simulator.add_event(ev1)
                self._simulator.add_event(ev2)
        else: # end-node
            _, qm = qmem.read(address=qubit.addr)
            qubit.fsm.to_release()
            log.debug(f"{self.own}: consume e2e entanglement: {qm.src.name} - {qm.dst.name}")
            self.e2e_count+=1
            from qns.network.protocol.event import QubitReleasedEvent
            event = QubitReleasedEvent(link_layer=self.link_layer, qubit=qubit, e2e=self.own.name=='S',
                                       t=self._simulator.tc, by=qmem)
            self._simulator.add_event(event)
            """ _, qm = qmem.get(address=qubit.addr)
            qm.rcvd+=1          # to track if both endnodes received last EPR results
            if qm.rcvd == 2:
                qmem.read(address=qubit.addr)
                log.debug(f"{self.own}: consume e2e entanglement: {qm.src.name} - {qm.dst.name}")
                from qns.network.protocol.event import QubitReleasedEvent, EndToEndEntanglementEvent
                qubit.fsm.to_release()
                event = QubitReleasedEvent(link_layer=self.link_layer, qubit=qubit, e2e=True,
                                       t=self._simulator.tc, by=qmem)

                partner = qm.dst if qm.src == self.own else qm.src
                nl_apps = partner.get_apps(self.__class__)
                if nl_apps:
                    partner_net_layer = nl_apps[0]
                event2 = EndToEndEntanglementEvent(net_layer=partner_net_layer, epr=qm.name,
                                                   t=self._simulator.tc, by=qmem)
                self._simulator.add_event(event)
                self._simulator.add_event(event2) """

    def send_swap_update(self, dest: Node, msg: Dict, route: List[str], delay: bool = False):
        log.debug(f"{self.own.name}: send_SU {dest} = {msg}")
        own_idx = route.index(self.own.name)        
        dest_idx = route.index(dest.name)

        nh = route[own_idx+1] if dest_idx > own_idx else route[own_idx-1]
        next_hop = self.own.network.get_node(nh)

        cchannel: ClassicChannel = self.own.get_cchannel(next_hop)
        if cchannel is None:
            raise Exception(f"{self.own}: No classic channel for dest {dest}")

        classic_packet = ClassicPacket(msg=msg, src=self.own, dest=dest)
        if delay:
            cchannel.send(classic_packet, next_hop=next_hop, delay=cchannel.delay_model.calculate())
        else:
            cchannel.send(classic_packet, next_hop=next_hop)
        # log.debug(f"{self.own}: send SWAP_UPDATE to {dest} via {next_hop}")


    def check_eligible_qubit(self, qmem: QuantumMemory, path_id: int = None):
        # assume isolated paths -> a path_id uses only left and right qmem
        for qm in self.memories:
            if qm.name != qmem.name:
                qubits = qm.search_eligible_qubits(pid=path_id)
                if qubits:
                    return qm, qubits
        return None, None
    
    def get_memory_qubit(self, epr_name: str):
        for qm in self.memories:
            res = qm.get(key=epr_name)
            if res is not None:
                return qm, res[0]
        return None, None

    def compute_qubit_allocation(self, path, m_v, node):
        if node not in path:
            return None, None           # Node not in path
        idx = path.index(node)
        prev_qubits = m_v[idx - 1] if idx > 0 else None  # Allocate from previous channel
        next_qubits = m_v[idx] if idx < len(m_v) else None  # Allocate for next channel
        return prev_qubits, next_qubits

    def handle_sync_signal(self, signal_type: SignalTypeEnum):
        log.debug(f"{self.own}:[{self.own.timing_mode}] TIMING SIGNAL <{signal_type}>")
        if self.own.timing_mode == TimingModeEnum.SYNC:
            self.sync_current_phase = signal_type
            if signal_type == SignalTypeEnum.INTERNAL:
                # handle all entangled qubits
                log.debug(f"{self.own}: there are {len(self.waiting_qubits)} etg qubits to process")
                for event in self.waiting_qubits:
                    self.handle_entangled_qubit(event)
                self.waiting_qubits = []
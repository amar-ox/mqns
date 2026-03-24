# Multiverse Quantum Network Simulator (MQNS)

![Build](https://github.com/usnistgov/mqns/actions/workflows/build.yml/badge.svg)
![Lint](https://github.com/usnistgov/mqns/actions/workflows/lint.yml/badge.svg)

## Overview

**Multiverse Quantum Network Simulator (MQNS)** is a research-focused quantum network simulator for evaluating entanglement routing under dynamic, heterogeneous network conditions. It provides a unified framework for rapidly prototyping and benchmarking entanglement distribution strategies and quantum network architectures.

MQNS enables systematic comparative studies across routing, swapping, purification, multiplexing, and resource-management designs.

![MQNS logo](docs/mqns-logo.svg)

This software is developed at the [Smart Connected Systems Division](https://www.nist.gov/ctl/smart-connected-systems-division) of the [National Institute of Standards and Technology (NIST)](https://www.nist.gov/).

## References

If you use MQNS in academic work, please cite the simulator paper and related routing survey:

- **Simulator paper**: [arXiv:2512.22937](https://arxiv.org/abs/2512.22937)
- **Survey**: [*Entanglement Routing in Quantum Networks: A Comprehensive Survey*](https://ieeexplore.ieee.org/document/10882978)

## Current Capabilities

### Routing Model

- Assumes **proactive centralized routing** (as defined in the survey taxonomy).
- Computes global paths at simulation startup using:
  - **Dijkstra's algorithm** for single-path routing.
  - **Yen's algorithm** for multipath routing.
- Supports installing/uninstalling paths at quantum routers; current emphasis is on the **forwarding phase**.

### Forwarding Phase Components

- **External and internal forwarding phases** in both synchronous and asynchronous modes.
- Elementary entanglement generation.
- Swapping and purification workflows.

#### Swapping Strategies

- Sequential and balanced-tree schemes.
- Parallel swap-as-soon-as-possible execution.
- Per-path [heuristic ad-hoc strategies](https://arxiv.org/abs/2504.14040).

#### Qubit Lifecycle and Multiplexing

- Tracks reservation, entanglement, intermediate state transitions, and release.
- Supports qubit-path multiplexing for:
  - Single or multiple source-destination requests.
  - Single or multiple paths.
- Includes **buffer-space** and **statistical multiplexing** ([reference](https://www.spiedigitallibrary.org/conference-proceedings-of-spie/8163/1/Multiplexing-schemes-for-quantum-repeater-networks/10.1117/12.893272.short)) and other dynamic entanglement allocation approaches.

#### Memory and Purification

- Memory-management policies for:
  - Assigning qubits to paths.
  - Selecting qubits to swap when multiple candidates are available.
- Partial support for purification policy controls, including:
  - Link/segment selection.
  - Number of purification rounds.
  - Bennett 96 protocol.

### Entanglement Link Model

- Elementary link modeling includes:
  - Werner-state EPR generation.
  - Probability-based sampling.
  - Duration estimates derived from entanglement link protocol characteristics.
- Supported link architectures:
  - Detection-in-Midpoint with single-rail encoding (2-round Barrett-Kok).
  - Detection-in-Midpoint with dual-rail polarization encoding.
  - Sender-Receiver with dual-rail polarization encoding.
  - Source-in-Midpoint with dual-rail polarization encoding.

## Roadmap

- Full purification support with configurable round limits or fidelity thresholds.
- Configurable memory-management and qubit-selection policies.
- Timeline-oriented logging and visualization for debugging and analysis.
- Runtime path computation and reconfiguration based on request arrivals.
- Additional routing models:
  - Reactive centralized routing.
  - Distributed proactive routing.
  - Distributed reactive routing.
- Ongoing refactoring for modularity, extensibility, and cleaner comparative evaluation workflows.

> ⚠️ MQNS is an active research project. APIs and behaviors may evolve.

## Relationship to SimQN

MQNS reuses selected components from [SimQN v0.1.5](https://github.com/QNLab-USTC/SimQN), which is licensed under the GNU General Public License v3.0 (GPLv3).

MQNS is **not** a fork of the official SimQN repository. It is a standalone project that incorporates a SimQN snapshot (including portions of the discrete-event simulation engine, noise modeling, and foundational structure), with substantial modifications for dynamic routing protocols and enhanced entanglement management.

As a result, MQNS is released under GPLv3. See [LICENSE](LICENSE) for details.

## Installation

MQNS is currently distributed as source for development use.

Clone the repository:

```bash
git clone https://github.com/usnistgov/mqns.git
cd mqns
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Option 1: Install from a local wheel

```bash
python -m build
pip install dist/mqns-0.1.0-py3-none-any.whl
```

### Option 2: Install in editable mode

```bash
pip install -e .
```

## Examples

The `examples/` directory contains runnable scripts for common MQNS experiments and workflows.

### Standard experiment examples

- **`3_nodes_thruput.py`**
  Three-node linear topology (`S -> R -> D`) throughput study versus memory coherence time.
  **Usage:** `python examples/3_nodes_thruput.py --mode P --epr_type W --link_arch DIM-BK-SeQUeNCe --runs 20 --csv out/3_nodes_thruput.csv --plt out/3_nodes_thruput.png`

- **`3_nodes_wait.py`**
  Single-repeater experiment with active fidelity enforcement using `T_wait`, reporting throughput and fidelity.
  **Usage:** `python examples/3_nodes_wait.py --epr_type W --link_arch DIM-BK-SeQUeNCe --runs 20 --t_wait 0.0025 0.005 0.01 --csv out/3_nodes_wait.csv --json out/3_nodes_wait.json --plt out/3_nodes_wait.png`

- **`asymmetric_channel_3_nodes.py`**
  Three-node asymmetric-channel study of memory allocation impact across link architectures.
  **Usage:** `python examples/asymmetric_channel_3_nodes.py --runs 10 --json out/asymmetric_channel_3_nodes.json --plt out/asymmetric_channel_3_nodes.png`

- **`swapping_policies_6_nodes.py`**
  Six-node linear-path comparison of swapping policies under different memory allocation schemes.
  **Usage:** `python examples/swapping_policies_6_nodes.py --runs 10 --json out/swapping_policies_6_nodes.json --plt out/swapping_policies_6_nodes.png`

- **`vora_evaluation.py`**
  Evaluation of swapping-order strategies (including VORA) on weighted linear paths.
  **Usage:** `python examples/vora_evaluation.py --runs 100 --total_distance 150 --t_cohere 0.01 --qchannel_capacity 25 --csv out/vora_evaluation.csv --plt out/vora_evaluation.png`

- **`scalability_randomtopo_plot.py`**
  Post-processing and plotting utility for random-topology scalability experiment outputs.
  **Usage:** `python examples/scalability_randomtopo_plot.py --indir out/scalability --runs 5 --qchannel_capacity 10 --csv out/scalability_summary.csv --plt out/scalability_plot.png`

### Quick-modify templates

These two templates are intended as starting points you can quickly customize to explore a wide range of scenarios.

- **`template_linear.py`** *(linear-topology template)*
  Starter script for linear-topology sweeps with configurable topology, link architecture, metrics, and output files.
  **Usage:** `python examples/template_linear.py --runs 20 --csv out/template_linear.csv --json out/template_linear.json --plt out/template_linear.png`

- **`template_routing.py`** *(routing + multiplexing template)*
  Starter script for custom-topology routing and multiplexing scenarios, including single-path, multi-flow, and multipath modes.
  **Usage:** `python examples/template_routing.py --runs 20`

> Note: The files `linear_attempts.py` and `scalability_randomtopo.py` are intentionally excluded from the short list above, per project guidance.

## Contributing and Feedback

Please open an issue to report bugs, request features, or discuss improvements.

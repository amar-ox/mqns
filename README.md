# SimQN++

SimQN++ is based on [SimQN](https://qnlab-ustc.github.io/SimQN/). It is a discrete-event network simulation platform for quantum networks.
SimQN enables large-scale investigations, including QKD protocols, entanglement distributions protocols, and routing algorithms, resource allocation schemas in quantum networks. For example, users can use SimQN to design routing algorithms for better QKD performance. For more information, please refer to [SimQN's documentation](https://qnlab-ustc.github.io/).

SimQN is a Python3 library for quantum networking simulation. It is designed to be general purpose. It means that SimQN can be used for both QKD network, entanglement distribution networks, and other kinds of quantum networks' evaluation. The core idea is that SimQN makes no architecture assumption. Since there is currently no recognized network architecture in quantum network investigations, SimQN stays flexible in this aspect.

SimQN provides high performance for large-scale network simulation. SimQN uses [Cython](https://cython.org/) to compile critical codes in C/C++ libraries to boost the evaluation. Also, along with the commonly used quantum state-based physical models, SimQN provides a higher-layer fidelity-based entanglement physical model to reduce the computation overhead and brings convenience for users in evaluation. Last but not least, SimQN provides several network auxiliary models for easily building network topologies, producing routing tables and managing multiple session requests.

## Get Help

- This [documentation](https://qnlab-ustc.github.io/SimQN/) may answer most questions.
    - The [tutorial](https://qnlab-ustc.github.io/SimQN/tutorials.html) here presents how to use SimQN.
    - The [API manual](https://qnlab-ustc.github.io/SimQN/modules.html) shows more detailed information.

- Welcome to report bugs at [Github](https://github.com/amar-ox/dynamic-qnetsim).


## Installation

This is a development version to be installed from source. 

First, checkout the source code from Github.

   `git checkout https://github.com/amar-ox/dynamic-qnetsim.git`
   `cd dynamic-qnetsim`

- Otional but recommended: create env
 - `cd`
 - `python3 -m venv simqn`
 - `source simqn/bin/activate`

- Alternative 1: install locally
Install setuptools as the package tool:
   `pip3 install setuptools wheel`

Build the package:
   `python3 setup.py bdist_wheel`

This command build the package and it should be located in the `dist` directory named `qns-0.1.5-py3-none-any.whl`. 

Finally, install the package to the system python library:
   `pip install --force-reinstall dist/qns-0.1.5-py3-none-any.whl`

- Alternative 2: install in edit mode
  `pip install -e .`

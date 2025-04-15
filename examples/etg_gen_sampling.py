import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import geom

def loss_based_success_prob(link_length_km, alpha_db_per_km=0.2, eta_d=0.95, eta_s=0.95):
    """Compute success probability from fiber loss model for heralded entanglement."""
    eta = 10 ** (-alpha_db_per_km * link_length_km / 10)
    p = eta * eta_d * eta_s  # one-photon sender-receiver
    return p

def skip_ahead_entanglement(p):
    """Return number of attempts until first success for given p."""
    return np.random.geometric(p)

# --- Parameters ---
L_km = 30
n_runs = 100000  # number of simulations

# --- Compute success probability ---
p = loss_based_success_prob(L_km)
print(f"Link Length: {L_km} km")
print(f"Derived Success Probability: {p:.3e}")
expected_attempts = 1 / p
print(f"Expected attempts: {expected_attempts:.1f}")

# --- Simulate many entanglement generation attempts ---
attempts_samples = np.array([skip_ahead_entanglement(p) for _ in range(n_runs)])

# --- Histogram parameters ---
max_k = int(np.percentile(attempts_samples, 99.5))  # display up to 99.5 percentile
bins = np.arange(1, max_k + 2) - 0.5  # for integer bin alignment

# --- Plot histogram ---
plt.figure(figsize=(10, 6))
plt.hist(attempts_samples, bins=bins, density=True, alpha=0.6, label="Simulated Histogram", color="skyblue", edgecolor='gray')

# --- Overlay theoretical PMF ---
x_vals = np.arange(1, max_k + 1)
pmf_vals = geom.pmf(x_vals, p)
plt.plot(x_vals, pmf_vals, 'r-', lw=2, label="Geometric PMF (theoretical)")

# --- Add labels and annotations ---
plt.title(f"Attempts Until First Entanglement (L = {L_km} km)")
plt.xlabel("Number of Attempts")
plt.ylabel("Probability Density")
plt.axvline(expected_attempts, color='red', linestyle='--', label=f'Expected: {expected_attempts:.0f}')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
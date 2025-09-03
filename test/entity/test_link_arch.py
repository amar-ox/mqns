import pytest

from qns.entity.qchannel import LinkArch, LinkArchDimBk, LinkArchSim, LinkArchSr


def check_link_arch(link_arch: LinkArch, *, attempt_duration: float, epr_creation: float, notify_a: float, notify_b: float):
    tau = 0.000471

    d1_epr_creation, d1_notify_a, d1_notify_b = link_arch.delays(1, reset_time=0.0, tau_l=tau, tau_0=0.0)
    assert d1_epr_creation == pytest.approx(epr_creation * tau, abs=1e-6)
    assert d1_notify_a == pytest.approx(notify_a * tau, abs=1e-6)
    assert d1_notify_b == pytest.approx(notify_b * tau, abs=1e-6)

    d6_epr_creation, _, _ = link_arch.delays(6, reset_time=0.0, tau_l=tau, tau_0=0.0)
    assert d6_epr_creation - d1_epr_creation == pytest.approx(5 * attempt_duration * tau, abs=1e-6)


def test_dim_bk():
    link_arch = LinkArchDimBk()
    check_link_arch(link_arch, attempt_duration=2, epr_creation=0, notify_a=2, notify_b=2)


def test_sr():
    link_arch = LinkArchSr()
    check_link_arch(link_arch, attempt_duration=2, epr_creation=0, notify_a=1, notify_b=2)


def test_sim():
    link_arch = LinkArchSim()
    check_link_arch(link_arch, attempt_duration=1, epr_creation=0, notify_a=1, notify_b=1)

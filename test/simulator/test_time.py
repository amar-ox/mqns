from pytest import approx

from qns.simulator.ts import Time, set_default_accuracy


def test_time():
    t1 = Time(1)
    t2 = Time(sec=1.1)
    t3 = Time()
    t4 = Time(1100000)

    print(t1.sec)
    print(t4)

    assert (t1 == t1)
    assert (t2 >= t1)
    assert (t1 <= t2)
    assert (t1 < t2)
    assert (t3 < t1)

def test_time_accuracy():
    t0 = Time(sec=1.0)

    class ChangeDefaultAccuracy:
        def __enter__(self):
            set_default_accuracy(2000)
        def __exit__(self, exc_type, exc_value, traceback):
            set_default_accuracy(t0.accuracy)

    with ChangeDefaultAccuracy():
        t1 = Time(sec=1.0)
        t2 = Time(sec=1.0, accuracy=3000)

    t3 = Time(sec=1.0)
    t4 = Time(sec=1.0, accuracy=4000)

    assert t0.sec == approx(1.0)
    assert t1.sec == approx(1.0)
    assert t2.sec == approx(1.0)
    assert t3.sec == approx(1.0)
    assert t4.sec == approx(1.0)

    assert t0.accuracy == t3.accuracy
    assert t1.accuracy == 2000
    assert t2.accuracy == 3000
    assert t4.accuracy == 4000

def print_msg(msg):
    print(msg)


def test_simulator_time():
    """
    If we modify the default_accuracy of the simulator,
    check whether the accuracy of subsequent events will be automatically synchronized with the simulator
    without special modification.
    """
    from qns.simulator.event import func_to_event
    from qns.simulator.simulator import Simulator
    s = Simulator(1, 10, 1000)
    s.run()
    print_event = func_to_event(Time(sec=1), print_msg, "hello world")
    print(print_event.t.accuracy)
    assert (print_event.t.accuracy == 1000)

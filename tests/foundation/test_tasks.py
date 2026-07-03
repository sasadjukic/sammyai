from threading import Event

from sammyai_core.tasks import BackgroundTaskRunner


def test_background_task_runner_executes_and_releases_task():
    runner = BackgroundTaskRunner()
    completed = Event()

    thread = runner.submit(completed.set, name="characterization")
    thread.join(timeout=2)

    assert completed.is_set()
    assert runner.active_count == 0

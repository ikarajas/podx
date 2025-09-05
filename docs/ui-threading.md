# UI Threading

Background services like `JobsService` execute work on worker threads and invoke
listeners from those threads. Qt widgets are not thread‑safe: touching them from
anything but the main GUI thread leads to undefined behaviour.

To update the UI from a worker callback, marshal the change onto the main
thread:

```python
from PyQt6.QtCore import QMetaObject, Qt

def _on_job_update(self, job):
    def apply():
        # update widgets here
        ...
    QMetaObject.invokeMethod(self.list, apply, Qt.ConnectionType.QueuedConnection)
```

Using `QTimer.singleShot` without a QObject target is unreliable because worker
threads do not have an event loop. Instead, rely on Qt signals or
`QMetaObject.invokeMethod(..., Qt.ConnectionType.QueuedConnection)` so the
callback executes on the GUI thread.

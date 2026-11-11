class Order:
    def __init__(
        self,
        job_id,
        priority,
        submit_time,
        status="processing",
        canceled_at=None,
    ):
        self.job_id = job_id
        self.priority = priority
        self.submit_time = submit_time
        self.status = status
        self.canceled_at = canceled_at


class OrderBatch:
    """A group of Jobs submitted together as one production order."""

    def __init__(
        self,
        order_id,
        submitted_at,
        job_ids,
        source="manual",
        canceled_at=None,
    ):
        self.order_id = str(order_id)
        self.submitted_at = float(submitted_at)
        self.job_ids = [int(job_id) for job_id in job_ids]
        self.source = str(source)
        self.canceled_at = canceled_at

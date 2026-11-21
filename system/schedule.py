from dataclasses import dataclass, field


@dataclass
class PlannedOperation:
    job_id: int
    operation_id: int
    machine_id: int
    start_time: float
    end_time: float
    source_machine: int | None = None
    transport_start: float | None = None
    transport_end: float | None = None
    transport_time: float = 0
    transport_energy: float = 0
    transport_segments: list = field(default_factory=list)
    waiting_time: float = 0
    status: str = "scheduled"
    stage_id: int | None = None
    stage_operation_id: int | None = None


class Schedule:
    def __init__(self, schedule_id, machine_count, schedule_items, start_time, end_time):
        self.schedule_id = schedule_id
        self.machine_count = machine_count
        self.schedule_items = schedule_items
        self.start_time = start_time
        self.end_time = end_time

    def addOperation(self, job_id, operation_id, machine_id, start_time, end_time):
        self.schedule_items[machine_id].append((job_id, operation_id))
        self.start_time[machine_id].append(start_time)
        self.end_time[machine_id].append(end_time)

    def sortedItems(self):
        """Return schedule entries in execution order for each machine."""
        for machine_id, items in enumerate(self.schedule_items):
            yield sorted(
                zip(
                    items,
                    self.start_time[machine_id],
                    self.end_time[machine_id],
                ),
                key=lambda item: (
                    item[1],
                    item[2],
                    item[0][0],
                    item[0][1],
                ),
            )

    def printItems(self, schedule_file, gantt_file, machines):
        output_str = ""
        for i, rows in enumerate(self.sortedItems()):
            output_str += "machine" + str(i) + ","
            for (job_id, operation_id), _, _ in rows:
                output_str += f"{job_id}-{operation_id},"
            output_str += "\nstart_time,"
            for _, start_time, _ in rows:
                output_str += f"{start_time},"
            output_str += "\nend_time,"
            for _, _, end_time in rows:
                output_str += f"{end_time},"
            output_str += "\n"
        with open(schedule_file, "w") as file:
            file.write(output_str)

        # 将结果编写成可供mermaidraw使用的甘特图格式
        gantt_str = "---\n"
        gantt_str += "displayMode: compact\n"
        gantt_str += "config:\n"
        gantt_str += "    themeCSS: |\n"
        gantt_str += "        .placeholder { fill: transparent; stroke: transparent; }\n"
        gantt_str += "    gantt:\n"
        gantt_str += "        barHeight: 120\n"
        gantt_str += "        useWidth: 2750\n"
        gantt_str += "        fontSize: 16\n"
        gantt_str += "        rightPadding: 0\n"
        gantt_str += "        numberSectionStyles: 1\n"
        gantt_str += "        sectionFontSize: 30\n"
        gantt_str += "---\n\n"
        gantt_str += "gantt\n"
        gantt_str += "    dateFormat  X\n"  
        gantt_str += "    axisFormat  %s\n"
        for i, rows in enumerate(self.sortedItems()):
            b = False
            gantt_str += f"    section Machine {i}\n"
            for (job_id, operation_id), start_time, end_time in rows:
                b = True
                gantt_str += f"        J{job_id}-{operation_id}: J{job_id}, {start_time}, {end_time}\n"
            if not b:
                gantt_str += f"        placeholder: placeholder, 0, 0\n"
        # 将甘特图字符串写入文件
        with open(gantt_file, "w") as gantt_file_obj:
            gantt_file_obj.write(gantt_str)

    def testSchedule(self):
        # Dynamic rescheduling appends entries in update order, which is not
        # necessarily chronological. Validate sorted execution intervals.
        for machine_id, rows in enumerate(self.sortedItems()):
            for index, (key, start_time, end_time) in enumerate(rows):
                if start_time >= end_time:
                    print(
                        f"machine {machine_id} operation {key} starts "
                        f"after it ends at {end_time}."
                    )
                if index == 0:
                    continue
                previous_key, _, previous_end = rows[index - 1]
                if start_time + 1e-9 < previous_end:
                    print(
                        f"machine {machine_id} operation {key} overlaps "
                        f"previous operation {previous_key} ending at "
                        f"{previous_end}."
                    )


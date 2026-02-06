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

    def printItems(self, schedule_file, gantt_file, machines):
        output_str = ""
        for i in range(self.machine_count):
            output_str += "machine" + str(i) + ","
            for j in range(len(self.schedule_items[i])):
                output_str += f"{self.schedule_items[i][j][0]}-{self.schedule_items[i][j][1]},"
            output_str += "\nstart_time,"
            for j in range(len(self.start_time[i])):
                output_str += f"{self.start_time[i][j]},"
            output_str += "\nend_time,"
            for j in range(len(self.end_time[i])):
                output_str += f"{self.end_time[i][j]},"
            output_str += "\n"
        with open(schedule_file, "w") as file:
            file.write(output_str)

        # 将结果编写成可供mermaidraw使用的甘特图格式
        gantt_str = "---\n"
        gantt_str += "displayMode: compact\n"
        gantt_str += "config:\n"
        gantt_str += "    themeCSS: |\n"
        gantt_str += "        #failure { fill: #cd4a1aff; stroke: #000000; stroke-width: 1px }\n"
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
        for i in range(self.machine_count):
            b = False
            gantt_str += f"    section Machine {i}\n"
            for j in range(len(self.schedule_items[i])):
                b = True
                job_id, operation_id = self.schedule_items[i][j]
                start_time = self.start_time[i][j]
                end_time = self.end_time[i][j]
                gantt_str += f"        J{job_id}-{operation_id}: J{job_id}, {start_time}, {end_time}\n"
            # 添加机器故障时间段
            for failure in machines[i].failures:
                b = True
                fail_start, fail_detect, fail_end = failure
                gantt_str += f"        F{i}: failure, {fail_detect}, {fail_end}\n"
            if not b:
                gantt_str += f"        placeholder: placeholder, 0, 0\n"
        # 将甘特图字符串写入文件
        with open(gantt_file, "w") as gantt_file_obj:
            gantt_file_obj.write(gantt_str)

    def testSchedule(self):
        # 比较每个机器的操作时间，确保没有重叠
        for i in range(self.machine_count):
            for j in range(1, len(self.schedule_items[i])):
                if self.start_time[i][j] < self.end_time[i][j - 1]:
                    print(f"machine {i} operation {self.schedule_items[i][j]} starts before previous operation ends at {self.end_time[i][j - 1]}.")
                if self.start_time[i][j] >= self.end_time[i][j]:
                    print(f"machine {i} operation {self.schedule_items[i][j]} starts after it ends at {self.end_time[i][j]}.")


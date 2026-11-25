//
// Created by luopw on 25-5-7.
//

#include "Experiment.h"
#include "DataProc.h"
#include "Schedule.h"

#include <algorithm>
#include <climits>
#include <cmath>
#include <fstream>
#include <iostream>
#include <queue>
#include <stdexcept>
#include <vector>

Schedule FIFO_EET(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList){
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    auto mchine_time = std::vector<int>(machineNum, 0);
    auto job_time = std::vector<int>(jobList.size(), 0);
    auto job_now_process = std::vector<int>(jobList.size(), 0);

    int process_count = 0;
    for(auto &jobName: jobList){
        auto job = SelectJobByJobName(jobs, jobName);
        process_count += job.get_process_count();
    }
    while(process_count > 0){
        // 获取最早完成工序的工件
        int min_time_job_index = -1;
        int min_time = INT_MAX;
        for(int i = 0; i < jobList.size(); i++){
            if(job_time[i] < min_time){
                min_time = job_time[i];
                min_time_job_index = i;
            }
        }
        auto job = SelectJobByJobName(jobs, jobList[min_time_job_index]);
        int process_id = job_now_process[min_time_job_index];
        job_now_process[min_time_job_index]++;

        // 获取process_id工序可选机器中最早完成的机器
        int min_machine_time = INT_MAX;
        int min_process_time = INT_MAX;
        Process_item min_machine_process;
        for(int i =0;i<job.get_job_process()[process_id].process_item.size(); i++){
            int machine_id = job.get_job_process()[process_id].process_item[i].machine_id;
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            if(mchine_time[machine_id] < min_machine_time)
            {
                min_machine_time = mchine_time[machine_id];
                min_machine_process = job.get_job_process()[process_id].process_item[i];
            }
            else if (mchine_time[machine_id] == min_machine_time && process_time < min_process_time)
            {
                min_process_time = process_time;
                min_machine_process = job.get_job_process()[process_id].process_item[i];
            }
        }
        schedule.AddProcess(min_machine_process.machine_id, job.get_job_id(), process_id);
        for(auto &machine: machines){
            if(machine.get_machine_id() == min_machine_process.machine_id){
                machine.set_process_count(machine.get_process_count() + 1);
                mchine_time[machine.get_machine_id()] += min_machine_process.process_time;
                break;
            }
        }
        if (job_now_process[min_time_job_index] == job.get_process_count()){
            job_time[min_time_job_index] = INT_MAX;
        } else {
            job_time[min_time_job_index] += min_machine_process.process_time;
        } 
        process_count--;
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

Schedule FIFO_SPT(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList)
{
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    auto mchine_time = std::vector<int>(machineNum, 0);
    auto job_time = std::vector<int>(jobList.size(), 0);
    auto job_now_process = std::vector<int>(jobList.size(), 0);

    int process_count = 0;
    for (auto &jobName : jobList)
    {
        auto job = SelectJobByJobName(jobs, jobName);
        process_count += job.get_process_count();
    }
    while (process_count > 0)
    {
        // 获取最早完成工序的工件
        int min_time_job_index = -1;
        int min_time = INT_MAX;
        for (int i = 0; i < jobList.size(); i++)
        {
            if (job_time[i] < min_time)
            {
                min_time = job_time[i];
                min_time_job_index = i;
            }
        }
        auto job = SelectJobByJobName(jobs, jobList[min_time_job_index]);
        int process_id = job_now_process[min_time_job_index];
        job_now_process[min_time_job_index]++;

        // 获取process_id工序可选机器中加工时间最短的工序
        int min_machine_time = INT_MAX;
        int min_process_time = INT_MAX;
        Process_item min_time_process;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size(); i++)
        {
            int machine_id = job.get_job_process()[process_id].process_item[i].machine_id;
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            if (process_time < min_process_time)
            {
                min_process_time = process_time;
                min_time_process = job.get_job_process()[process_id].process_item[i];
            }
            else if (process_time == min_process_time && mchine_time[machine_id] < min_machine_time)
            {
                min_machine_time = mchine_time[machine_id];
                min_time_process = job.get_job_process()[process_id].process_item[i];
            }
        }
        schedule.AddProcess(min_time_process.machine_id, job.get_job_id(), process_id);
        for (auto &machine : machines)
        {
            if (machine.get_machine_id() == min_time_process.machine_id)
            {
                machine.set_process_count(machine.get_process_count() + 1);
                mchine_time[machine.get_machine_id()] += min_time_process.process_time;
                break;
            }
        }
        if (job_now_process[min_time_job_index] == job.get_process_count())
        {
            job_time[min_time_job_index] = INT_MAX;
        }
        else
        {
            job_time[min_time_job_index] += min_time_process.process_time;
        }
        process_count--;
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

Schedule MOPNR_EET(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList){
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    auto mchine_time = std::vector<int>(machineNum, 0);
    auto job_time = std::vector<int>(jobList.size(), 0);
    auto job_now_process = std::vector<int>(jobList.size(), 0);
    auto job_process_count = std::vector<int>(jobList.size(), 0);

    int process_count = 0;
    for (auto &jobName : jobList)
    {
        auto job = SelectJobByJobName(jobs, jobName);
        process_count += job.get_process_count();
        job_process_count[job.get_job_id()] = job.get_process_count();
    }
    while (process_count > 0)
    {
        // 获取最早完成工序的工件
        int max_process_count_job_index = -1;
        int max_process_count = INT_MIN;
        for (int i = 0; i < jobList.size(); i++)
        {
            if (job_process_count[i] > max_process_count)
            {
                max_process_count = job_process_count[i];
                max_process_count_job_index = i;
            }
        }
        auto job = SelectJobByJobName(jobs, jobList[max_process_count_job_index]);
        int process_id = job_now_process[max_process_count_job_index];
        job_now_process[max_process_count_job_index]++;
        job_process_count[max_process_count_job_index]--;

        // 获取process_id工序可选机器中最早完成的机器
        int min_machine_time = INT_MAX;
        int min_process_time = INT_MAX;
        Process_item min_machine_process;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size(); i++)
        {
            int machine_id = job.get_job_process()[process_id].process_item[i].machine_id;
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            if (mchine_time[machine_id] < min_machine_time)
            {
                min_machine_time = mchine_time[machine_id];
                min_machine_process = job.get_job_process()[process_id].process_item[i];
            }
            else if (mchine_time[machine_id] == min_machine_time && process_time < min_process_time)
            {
                min_process_time = process_time;
                min_machine_process = job.get_job_process()[process_id].process_item[i];
            }
        }
        schedule.AddProcess(min_machine_process.machine_id, job.get_job_id(), process_id);
        for (auto &machine : machines)
        {
            if (machine.get_machine_id() == min_machine_process.machine_id)
            {
                machine.set_process_count(machine.get_process_count() + 1);
                mchine_time[machine.get_machine_id()] += min_machine_process.process_time;
                break;
            }
        }
        if (job_now_process[max_process_count_job_index] == job.get_process_count())
        {
            job_time[max_process_count_job_index] = INT_MAX;
        }
        else
        {
            job_time[max_process_count_job_index] += min_machine_process.process_time;
        }
        process_count--;
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

Schedule MOPNR_SPT(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList)
{
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    auto mchine_time = std::vector<int>(machineNum, 0);
    auto job_time = std::vector<int>(jobList.size(), 0);
    auto job_now_process = std::vector<int>(jobList.size(), 0);
    auto job_process_count = std::vector<int>(jobList.size(), 0);

    int process_count = 0;
    for (auto &jobName : jobList)
    {
        auto job = SelectJobByJobName(jobs, jobName);
        process_count += job.get_process_count();
        job_process_count[job.get_job_id()] = job.get_process_count();
    }
    while (process_count > 0)
    {
        // 获取最早完成工序的工件
        int max_process_count_job_index = -1;
        int max_process_count = INT_MIN;
        for (int i = 0; i < jobList.size(); i++)
        {
            if (job_process_count[i] > max_process_count)
            {
                max_process_count = job_process_count[i];
                max_process_count_job_index = i;
            }
        }
        auto job = SelectJobByJobName(jobs, jobList[max_process_count_job_index]);
        int process_id = job_now_process[max_process_count_job_index];
        job_now_process[max_process_count_job_index]++;
        job_process_count[max_process_count_job_index]--;

        // 获取process_id工序可选机器中加工时间最短的工序
        int min_machine_time = INT_MAX;
        int min_process_time = INT_MAX;
        Process_item min_time_process;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size(); i++)
        {
            int machine_id = job.get_job_process()[process_id].process_item[i].machine_id;
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            if (process_time < min_process_time)
            {
                min_process_time = process_time;
                min_time_process = job.get_job_process()[process_id].process_item[i];
            }
            else if (process_time == min_process_time && mchine_time[machine_id] < min_machine_time)
            {
                min_machine_time = mchine_time[machine_id];
                min_time_process = job.get_job_process()[process_id].process_item[i];
            }
        }
        schedule.AddProcess(min_time_process.machine_id, job.get_job_id(), process_id);
        for (auto &machine : machines)
        {
            if (machine.get_machine_id() == min_time_process.machine_id)
            {
                machine.set_process_count(machine.get_process_count() + 1);
                mchine_time[machine.get_machine_id()] += min_time_process.process_time;
                break;
            }
        }
        if (job_now_process[max_process_count_job_index] == job.get_process_count())
        {
            job_time[max_process_count_job_index] = INT_MAX;
        }
        else
        {
            job_time[max_process_count_job_index] += min_time_process.process_time;
        }
        process_count--;
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

Schedule MWKR_EET(std::vector<Job> & jobs, std::vector<Machine> & machines, std::vector<std::string> & jobList)
{
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    auto mchine_time = std::vector<int>(machineNum, 0);
    auto job_time = std::vector<int>(jobList.size(), 0);
    auto job_now_process = std::vector<int>(jobList.size(), 0);
    auto job_time_remain = std::vector<int>(jobList.size(), 0);

    int process_count = 0;
    for (auto &jobName : jobList)
    {
        auto job = SelectJobByJobName(jobs, jobName);
        process_count += job.get_process_count();
        int total_time = job.getTotalAverageProcessTime();
        job_time_remain[job.get_job_id()] = total_time;
    }
    while (process_count > 0)
    {
        // 获取最早完成工序的工件
        int max_time_remain_job_index = -1;
        int max_time_remain = INT_MIN;
        for (int i = 0; i < jobList.size(); i++)
        {
            if (job_time_remain[i] > max_time_remain)
            {
                max_time_remain = job_time_remain[i];
                max_time_remain_job_index = i;
            }
        }
        auto job = SelectJobByJobName(jobs, jobList[max_time_remain_job_index]);
        int process_id = job_now_process[max_time_remain_job_index];
        job_now_process[max_time_remain_job_index]++;
        int process_average_time = 0;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size();i++){
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            process_average_time += process_time;
        }
        process_average_time /= job.get_job_process()[process_id].machine_count;
        job_time_remain[max_time_remain_job_index] -= process_average_time;

        // 获取process_id工序可选机器中最早完成的机器
        int min_machine_time = INT_MAX;
        int min_process_time = INT_MAX;
        Process_item min_machine_process;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size(); i++)
        {
            int machine_id = job.get_job_process()[process_id].process_item[i].machine_id;
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            if (mchine_time[machine_id] < min_machine_time)
            {
                min_machine_time = mchine_time[machine_id];
                min_machine_process = job.get_job_process()[process_id].process_item[i];
            }
            else if (mchine_time[machine_id] == min_machine_time && process_time < min_process_time)
            {
                min_process_time = process_time;
                min_machine_process = job.get_job_process()[process_id].process_item[i];
            }
        }
        schedule.AddProcess(min_machine_process.machine_id, job.get_job_id(), process_id);
        for (auto &machine : machines)
        {
            if (machine.get_machine_id() == min_machine_process.machine_id)
            {
                machine.set_process_count(machine.get_process_count() + 1);
                mchine_time[machine.get_machine_id()] += min_machine_process.process_time;
                break;
            }
        }
        if (job_now_process[max_time_remain_job_index] == job.get_process_count())
        {
            job_time[max_time_remain_job_index] = INT_MAX;
            job_time_remain[max_time_remain_job_index] = 0;
        }
        else
        {
            job_time[max_time_remain_job_index] += min_machine_process.process_time;
        }
        process_count--;
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

Schedule MWKR_SPT(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList)
{
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    auto mchine_time = std::vector<int>(machineNum, 0);
    auto job_time = std::vector<int>(jobList.size(), 0);
    auto job_now_process = std::vector<int>(jobList.size(), 0);
    auto job_time_remain = std::vector<int>(jobList.size(), 0);

    int process_count = 0;
    for (auto &jobName : jobList)
    {
        auto job = SelectJobByJobName(jobs, jobName);
        process_count += job.get_process_count();
        int total_time = job.getTotalAverageProcessTime();
        job_time_remain[job.get_job_id()] = total_time;
    }
    while (process_count > 0)
    {
        // 获取最早完成工序的工件
        int max_time_remain_job_index = -1;
        int max_time_remain = INT_MIN;
        for (int i = 0; i < jobList.size(); i++)
        {
            if (job_time_remain[i] > max_time_remain)
            {
                max_time_remain = job_time_remain[i];
                max_time_remain_job_index = i;
            }
        }
        auto job = SelectJobByJobName(jobs, jobList[max_time_remain_job_index]);
        int process_id = job_now_process[max_time_remain_job_index];
        job_now_process[max_time_remain_job_index]++;
        int process_average_time = 0;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size(); i++)
        {
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            process_average_time += process_time;
        }
        process_average_time /= job.get_job_process()[process_id].machine_count;
        job_time_remain[max_time_remain_job_index] -= process_average_time;

        // 获取process_id工序可选机器中加工时间最短的工序
        int min_machine_time = INT_MAX;
        int min_process_time = INT_MAX;
        Process_item min_time_process;
        for (int i = 0; i < job.get_job_process()[process_id].process_item.size(); i++)
        {
            int machine_id = job.get_job_process()[process_id].process_item[i].machine_id;
            int process_time = job.get_job_process()[process_id].process_item[i].process_time;
            if (process_time < min_process_time)
            {
                min_process_time = process_time;
                min_time_process = job.get_job_process()[process_id].process_item[i];
            }
            else if (process_time == min_process_time && mchine_time[machine_id] < min_machine_time)
            {
                min_machine_time = mchine_time[machine_id];
                min_time_process = job.get_job_process()[process_id].process_item[i];
            }
        }
        schedule.AddProcess(min_time_process.machine_id, job.get_job_id(), process_id);
        for (auto &machine : machines)
        {
            if (machine.get_machine_id() == min_time_process.machine_id)
            {
                machine.set_process_count(machine.get_process_count() + 1);
                mchine_time[machine.get_machine_id()] += min_time_process.process_time;
                break;
            }
        }
        if (job_now_process[max_time_remain_job_index] == job.get_process_count())
        {
            job_time[max_time_remain_job_index] = INT_MAX;
            job_time_remain[max_time_remain_job_index] = 0;
        }
        else
        {
            job_time[max_time_remain_job_index] +=  min_time_process.process_time;
        }
        process_count--;
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true,  machines);
    schedule.set_schedule_id(0);
    return schedule;
}

namespace {

int TransportTime(const int from_machine, const int to_machine) {
    if (from_machine < 0 || from_machine == to_machine) {
        return 0;
    }
    if (Machine::transport_time_matrix.empty()) {
        return 0;
    }
    return Machine::transport_time_matrix[from_machine][to_machine];
}

int TransportEnergy(const int from_machine, const int to_machine) {
    if (from_machine < 0 || from_machine == to_machine) {
        return 0;
    }
    if (Machine::transport_energy_matrix.empty()) {
        return 0;
    }
    return Machine::transport_energy_matrix[from_machine][to_machine];
}

int MaxTransportTime() {
    int max_transport = 1;
    for (const auto &row : Machine::transport_time_matrix) {
        for (const int value : row) {
            max_transport = std::max(max_transport, value);
        }
    }
    return max_transport;
}

void ResetMachineProcessCounts(std::vector<Machine> &machines) {
    for (auto &machine : machines) {
        machine.set_process_count(0);
    }
}

Schedule CreateEmptySchedule(const int machine_num) {
    Schedule schedule;
    schedule.set_machine_count(machine_num);
    std::vector<Schedule_item> schedule_items;
    schedule_items.reserve(machine_num);
    for (int i = 0; i < machine_num; ++i) {
        Schedule_item schedule_item;
        schedule_item.machine_id = i;
        schedule_item.process_count = 0;
        schedule_item.schedule_process.clear();
        schedule_items.push_back(schedule_item);
    }
    schedule.set_schedule_items(schedule_items);
    return schedule;
}

int EstimateRemainingWork(const Job &job, const int from_process_id) {
    int remaining = 0;
    for (int process_id = from_process_id; process_id < job.get_process_count(); ++process_id) {
        int min_process_time = INT_MAX;
        for (const auto &candidate : job.get_job_process()[process_id].process_item) {
            min_process_time = std::min(min_process_time, candidate.process_time);
        }
        if (min_process_time != INT_MAX) {
            remaining += min_process_time;
        }
    }
    return remaining;
}

double ComputeLoadAverage(const std::vector<int> &machine_load) {
    if (machine_load.empty()) {
        return 1.0;
    }
    long long load_sum = 0;
    for (const int load : machine_load) {
        load_sum += load;
    }
    return std::max(1.0, static_cast<double>(load_sum) / machine_load.size());
}

struct CandidateAssignment {
    Process_item process;
    int end_time = 0;
    double machine_score = 0.0;
};

CandidateAssignment SelectMachineByInfluence(
    const Job &job,
    const int process_id,
    const int prev_machine,
    const int job_ready,
    const std::vector<int> &machine_avail,
    const std::vector<int> &machine_load,
    const double load_avg,
    const int tau_max) {
    const auto &process_items = job.get_job_process()[process_id].process_item;

    int min_process_time = INT_MAX;
    int min_energy = INT_MAX;
    for (const auto &candidate : process_items) {
        min_process_time = std::min(min_process_time, candidate.process_time);
        min_energy = std::min(min_energy, candidate.processing_energy);
    }
    min_process_time = std::max(1, min_process_time);
    min_energy = std::max(1, min_energy);

    CandidateAssignment best;
    best.machine_score = 1e100;
    best.end_time = INT_MAX;
    best.process = process_items[0];

    for (const auto &candidate : process_items) {
        const int transport = TransportTime(prev_machine, candidate.machine_id);
        const int transport_energy = TransportEnergy(prev_machine, candidate.machine_id);
        int start_time = machine_avail[candidate.machine_id];
        const int arrival_time = job_ready + transport;
        if (arrival_time > start_time) {
            start_time = arrival_time;
        }
        const int end_time = start_time + candidate.process_time;

        const double time_ratio = static_cast<double>(candidate.process_time) / min_process_time;
        const double energy_ratio = static_cast<double>(candidate.processing_energy + transport_energy) / min_energy;
        const double load_ratio = machine_load[candidate.machine_id] / load_avg;
        const double queue_ratio = static_cast<double>(machine_avail[candidate.machine_id]) /
                                   std::max(1.0, load_avg);
        const double transport_ratio = static_cast<double>(transport) / tau_max;

        // 加工效率、能耗权衡、资源拥堵/排队、运输路径 —— 对应 method.md 3.1 / 3.3
        const double score = 0.30 * time_ratio +
                             0.20 * energy_ratio +
                             0.25 * (0.5 * load_ratio + 0.5 * queue_ratio) +
                             0.25 * transport_ratio;

        const bool better_score = score < best.machine_score - 1e-9;
        const bool similar_score = std::fabs(score - best.machine_score) <= 0.05;
        if (better_score ||
            (similar_score && end_time < best.end_time) ||
            (similar_score && end_time == best.end_time &&
             candidate.processing_energy < best.process.processing_energy)) {
            best.machine_score = score;
            best.end_time = end_time;
            best.process = candidate;
        }
    }

    return best;
}

double ComputeUrgencyFactor(const Job &job, const int job_ready, const int remain_work) {
    int slack = job.get_due_time() - (job_ready + remain_work);
    double urgency = static_cast<double>(job.get_weight() * job.get_tardiness_cost()) /
                     std::max(1, slack);
    if (slack <= 0) {
        urgency *= 1.0 + static_cast<double>(-slack) / std::max(1, job.get_due_time());
    }
    return urgency;
}

double ComputeCriticalityFactor(const int remain_work, const int process_time) {
    return static_cast<double>(remain_work) / std::max(1, process_time);
}

void ApplyFifoBaseline(Schedule &schedule, const Schedule &fifo_baseline) {
    schedule.set_fifo_total_time(fifo_baseline.get_fifo_total_time());
    schedule.set_fifo_earliness_tardiness_cost(fifo_baseline.get_fifo_earliness_tardiness_cost());
    schedule.set_fifo_energy_cost(fifo_baseline.get_fifo_energy_cost());
    CalculateCombinedObjective(schedule);
}

Schedule BuildFifoBaseline(
    std::vector<Job> &jobs,
    std::vector<Machine> machines,
    std::vector<std::string> &jobList) {
    Schedule fifo_baseline = FIFO_SPT(jobs, machines, jobList);
    fifo_baseline.set_fifo_total_time(fifo_baseline.get_TotalTime());
    fifo_baseline.set_fifo_earliness_tardiness_cost(fifo_baseline.get_total_earliness_tardiness_cost());
    fifo_baseline.set_fifo_energy_cost(fifo_baseline.get_total_energy_cost());
    CalculateCombinedObjective(fifo_baseline);
    return fifo_baseline;
}

InitialMethodMetrics BuildMethodMetrics(
    const std::string &method_name,
    const Schedule &schedule) {
    InitialMethodMetrics metrics;
    metrics.method_name = method_name;
    metrics.makespan = schedule.get_TotalTime();
    metrics.cost = schedule.get_total_earliness_tardiness_cost();
    metrics.energy = schedule.get_total_energy_cost();
    metrics.combined_objective = schedule.get_combined_objective();
    return metrics;
}

} // namespace

const std::vector<std::string> &InitialMethodNames() {
    static const std::vector<std::string> methods = {
        "FIFO_SPT",
        "FIFO_EET",
        "MOPNR_SPT",
        "MOPNR_EET",
        "MWKR_SPT",
        "MWKR_EET",
        "InfluenceAwareConstruct",
    };
    return methods;
}

std::string NormalizeInitialMethodName(const std::string &method_name) {
    if (method_name == "InfluenceAware" ||
        method_name == "InfluenceAwareConstruct") {
        return "InfluenceAwareConstruct";
    }
    for (const auto &name : InitialMethodNames()) {
        if (method_name == name) {
            return name;
        }
    }
    return "";
}

Schedule RunInitialMethod(
    const std::string &method_name,
    std::vector<Job> &jobs,
    std::vector<Machine> &machines,
    std::vector<std::string> &jobList) {
    const std::string normalized = NormalizeInitialMethodName(method_name);
    if (normalized == "FIFO_SPT") {
        return FIFO_SPT(jobs, machines, jobList);
    }
    if (normalized == "FIFO_EET") {
        return FIFO_EET(jobs, machines, jobList);
    }
    if (normalized == "MOPNR_SPT") {
        return MOPNR_SPT(jobs, machines, jobList);
    }
    if (normalized == "MOPNR_EET") {
        return MOPNR_EET(jobs, machines, jobList);
    }
    if (normalized == "MWKR_SPT") {
        return MWKR_SPT(jobs, machines, jobList);
    }
    if (normalized == "MWKR_EET") {
        return MWKR_EET(jobs, machines, jobList);
    }
    if (normalized == "InfluenceAwareConstruct") {
        return InfluenceAwareConstruct(jobs, machines, jobList);
    }
    throw std::invalid_argument("Unsupported initial scheduling method: " + method_name);
}

Schedule InfluenceAwareConstruct(
    std::vector<Job> &jobs,
    std::vector<Machine> &machines,
    std::vector<std::string> &jobList) {
    const int machine_num = static_cast<int>(machines.size());
    const int job_num = static_cast<int>(jobList.size());
    Schedule schedule = CreateEmptySchedule(machine_num);

    ResetMachineProcessCounts(machines);

    std::vector<int> machine_avail(machine_num, 0);
    std::vector<int> machine_load(machine_num, 0);
    std::vector<int> job_now_process(job_num, 0);
    std::vector<int> job_ready_time(job_num, 0);
    std::vector<int> last_machine(job_num, -1);

    for (int i = 0; i < job_num; ++i) {
        job_ready_time[i] = SelectJobByJobName(jobs, jobList[i]).get_ready_time();
    }

    struct PoolEntry {
        int job_index;
        int process_id;
    };

    std::vector<PoolEntry> pool;
    pool.reserve(job_num);
    for (int i = 0; i < job_num; ++i) {
        pool.push_back({i, 0});
    }

    const int tau_max = MaxTransportTime();
    int total_ops = 0;
    for (int i = 0; i < job_num; ++i) {
        total_ops += SelectJobByJobName(jobs, jobList[i]).get_process_count();
    }

    while (!pool.empty()) {
        const double load_avg = ComputeLoadAverage(machine_load);

        struct ScoredEntry {
            PoolEntry entry;
            CandidateAssignment assignment;
            double urgency;
            double criticality;
        };

        std::vector<ScoredEntry> scored_entries;
        scored_entries.reserve(pool.size());

        for (const auto &entry : pool) {
            const Job job = SelectJobByJobName(jobs, jobList[entry.job_index]);
            const int prev_machine = last_machine[entry.job_index];
            const int job_ready = job_ready_time[entry.job_index];
            const int remain_work = EstimateRemainingWork(job, entry.process_id);

            const CandidateAssignment assignment = SelectMachineByInfluence(
                job,
                entry.process_id,
                prev_machine,
                job_ready,
                machine_avail,
                machine_load,
                load_avg,
                tau_max);

            scored_entries.push_back({
                entry,
                assignment,
                ComputeUrgencyFactor(job, job_ready, remain_work),
                ComputeCriticalityFactor(remain_work, assignment.process.process_time),
            });
        }

        std::sort(scored_entries.begin(), scored_entries.end(), [](const ScoredEntry &lhs, const ScoredEntry &rhs) {
            if (lhs.assignment.end_time != rhs.assignment.end_time) {
                return lhs.assignment.end_time < rhs.assignment.end_time;
            }
            if (lhs.urgency != rhs.urgency) {
                return lhs.urgency > rhs.urgency;
            }
            return lhs.criticality > rhs.criticality;
        });

        const ScoredEntry &chosen = scored_entries.front();
        const Job chosen_job = SelectJobByJobName(jobs, jobList[chosen.entry.job_index]);
        const int chosen_job_index = chosen.entry.job_index;
        const int chosen_process_id = chosen.entry.process_id;

        schedule.AddProcess(
            chosen.assignment.process.machine_id,
            chosen_job.get_job_id(),
            chosen_process_id);

        for (auto &machine : machines) {
            if (machine.get_machine_id() == chosen.assignment.process.machine_id) {
                machine.set_process_count(machine.get_process_count() + 1);
                break;
            }
        }

        machine_avail[chosen.assignment.process.machine_id] = chosen.assignment.end_time;
        machine_load[chosen.assignment.process.machine_id] += chosen.assignment.process.process_time;
        last_machine[chosen_job_index] = chosen.assignment.process.machine_id;
        job_ready_time[chosen_job_index] = chosen.assignment.end_time;
        job_now_process[chosen_job_index]++;

        pool.erase(
            std::remove_if(
                pool.begin(),
                pool.end(),
                [&](const PoolEntry &pool_entry) {
                    return pool_entry.job_index == chosen_job_index &&
                           pool_entry.process_id == chosen_process_id;
                }),
            pool.end());

        if (job_now_process[chosen_job_index] < chosen_job.get_process_count()) {
            pool.push_back({chosen_job_index, job_now_process[chosen_job_index]});
        }

        total_ops--;
        if (total_ops < 0) {
            break;
        }
    }

    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

InitialComparisonResult CompareInitialMethods(
    std::vector<Job> &jobs,
    const std::vector<Machine> &machines_template,
    std::vector<std::string> &jobList) {
    InitialComparisonResult result;
    result.fifo_baseline = BuildFifoBaseline(jobs, machines_template, jobList);

    struct MethodRunner {
        std::string name;
        Schedule (*runner)(std::vector<Job> &, std::vector<Machine> &, std::vector<std::string> &);
    };

    const MethodRunner methods[] = {
        {"FIFO_SPT", FIFO_SPT},
        {"FIFO_EET", FIFO_EET},
        {"MOPNR_SPT", MOPNR_SPT},
        {"MOPNR_EET", MOPNR_EET},
        {"MWKR_SPT", MWKR_SPT},
        {"MWKR_EET", MWKR_EET},
        {"InfluenceAwareConstruct", InfluenceAwareConstruct},
    };

    double best_objective = 1e100;
    for (const auto &method : methods) {
        std::vector<Machine> method_machines = machines_template;
        Schedule schedule = method.runner(jobs, method_machines, jobList);
        ApplyFifoBaseline(schedule, result.fifo_baseline);
        result.methods.push_back(BuildMethodMetrics(method.name, schedule));

        if (schedule.get_combined_objective() < best_objective) {
            best_objective = schedule.get_combined_objective();
            result.best_method = method.name;
            result.best_schedule = schedule;
        }
    }

    return result;
}

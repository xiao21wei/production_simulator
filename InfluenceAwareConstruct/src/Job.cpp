//
// Created by luopw on 24-12-1.
//

#include "Job.h"
#include <iostream>


Job::Job() {
    job_id = 0;
    job_name = "";
    process_count = 0;
    job_process.clear();
    ready_time = 0;
    due_time = 0;
    earliness_cost = 0;
    tardiness_cost = 0;
    weight = 0;
}
int Job::get_job_id() const {return job_id;}
const std::string &Job::get_job_name() const {return job_name;}
int Job::get_process_count() const {return process_count;}
const std::vector<Job_process> &Job::get_job_process() const {return job_process;}
int Job::get_ready_time() const {return ready_time;}
int Job::get_due_time() const {return due_time;}
int Job::get_earliness_cost() const {return earliness_cost;}
int Job::get_tardiness_cost() const {return tardiness_cost;}
int Job::get_weight() const {return weight;}
void Job::set_job_id(const int job_id) {this->job_id = job_id;}
void Job::set_job_name(const std::string &job_name) {this->job_name = job_name;}
void Job::set_process_count(const int process_count) {this->process_count = process_count;}
void Job::set_job_process(const std::vector<Job_process> &job_process) {this->job_process = job_process;}
void Job::set_ready_time(const int ready_time) {this->ready_time = ready_time;}
void Job::set_due_time(const int due_time) {this->due_time = due_time;}
void Job::set_earliness_cost(const int earliness_cost) {this->earliness_cost = earliness_cost;}
void Job::set_tardiness_cost(const int tardiness_cost) {this->tardiness_cost = tardiness_cost;}
void Job::set_weight(const int weight) {this->weight = weight;}
void Job::to_string() {
    std::cout << "job_id: " << job_id << ", job_name: " << job_name << ", process_count: " << process_count << std::endl;
    for (auto &[machine_count, process_item] : job_process) {
        std::cout << "machine_count: " << machine_count << std::endl;
        for (auto &[process_id, machine_id, process_time, processing_energy] : process_item) {
            std::cout << "process_id: " << process_id << ", machine_id: " << machine_id << ", process_time: " << process_time << ", processing_energy: " << processing_energy << std::endl;
        }
    }
}

int Job::getTotalAverageProcessTime() const {
    int total_time = 0;
    for (auto &[machine_count, process_item] : job_process) {
        int temp_time =0 ;
        for (auto &[process_id, machine_id, process_time, processing_energy] : process_item) {
            temp_time += process_time;
        }
        total_time += temp_time / machine_count;
    }
    // std::cout << "total_time: " << total_time << std::endl;
    return total_time;
}

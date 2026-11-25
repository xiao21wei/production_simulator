#include <iostream>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <vector>
#include <utility>

#include "DataProc.h"
#include "ConstructionApi.h"
#include "GreedySearch.h"
#include "RandomSearch.h"
#include "Schedule.h"
#include "Job.h"
#include "Machine.h"
#include "Order.h"
#include "Experiment.h"
#include <string.h>

using namespace std;

double hv_2d_min(double points_2d[][2], int n_points, double ref_2d[2]) {
    if (n_points == 0) return 0.0;
    
    std::vector<std::pair<double, double>> valid_points;
    for (int i = 0; i < n_points; i++) {
        if (points_2d[i][0] < ref_2d[0] && points_2d[i][1] < ref_2d[1]) {
            valid_points.emplace_back(points_2d[i][0], points_2d[i][1]);
        }
    }
    
    if (valid_points.empty()) return 0.0;
    
    std::sort(valid_points.begin(), valid_points.end());
    
    double area = 0.0;
    double best_y = ref_2d[1];
    for (const auto &p : valid_points) {
        double x = p.first;
        double y = p.second;
        if (y < best_y) {
            area += std::max(ref_2d[0] - x, 0.0) * std::max(best_y - y, 0.0);
            best_y = y;
        }
    }
    return area;
}

double hv_3d_min(double points_3d[][3], int n_points, double ref_3d[3]) {
    if (n_points == 0) return 0.0;
    
    std::vector<std::vector<double>> valid_points;
    for (int i = 0; i < n_points; i++) {
        if (points_3d[i][0] < ref_3d[0] && 
            points_3d[i][1] < ref_3d[1] && 
            points_3d[i][2] < ref_3d[2]) {
            valid_points.push_back({points_3d[i][0], points_3d[i][1], points_3d[i][2]});
        }
    }
    
    if (valid_points.empty()) return 0.0;
    
    std::sort(valid_points.begin(), valid_points.end(), [](const std::vector<double> &a, const std::vector<double> &b) {
        return a[2] < b[2];
    });
    
    std::vector<double> z_levels;
    for (const auto &p : valid_points) {
        if (z_levels.empty() || z_levels.back() != p[2]) {
            z_levels.push_back(p[2]);
        }
    }
    
    double volume = 0.0;
    int n_z = z_levels.size();
    for (int i_z = 0; i_z < n_z; i_z++) {
        double z_low = z_levels[i_z];
        double z_high = (i_z + 1 < n_z) ? z_levels[i_z + 1] : ref_3d[2];
        if (z_high <= z_low) continue;
        
        std::vector<std::pair<double, double>> active_xy;
        for (const auto &p : valid_points) {
            if (p[2] <= z_low) {
                active_xy.emplace_back(p[0], p[1]);
            }
        }
        
        if (active_xy.empty()) continue;
        
        std::sort(active_xy.begin(), active_xy.end());
        double area_xy = 0.0;
        double best_y = ref_3d[1];
        for (const auto &p : active_xy) {
            double x = p.first;
            double y = p.second;
            if (y < best_y) {
                area_xy += std::max(ref_3d[0] - x, 0.0) * std::max(best_y - y, 0.0);
                best_y = y;
            }
        }
        volume += area_xy * (z_high - z_low);
    }
    return volume;
}

double CalculateHV(const Schedule &schedule) {
    double ratio_time = static_cast<double>(schedule.get_TotalTime()) / schedule.get_fifo_total_time();
    double ratio_cost = static_cast<double>(schedule.get_total_earliness_tardiness_cost()) / schedule.get_fifo_earliness_tardiness_cost();
    double ratio_energy = static_cast<double>(schedule.get_total_energy_cost()) / schedule.get_fifo_energy_cost();

    double points_3d[1][3] = {{ratio_time, ratio_cost, ratio_energy}};
    double ref_3d[3] = {1.0, 1.0, 1.0};

    return hv_3d_min(points_3d, 1, ref_3d);
}

int main(int argc, char *argv[]) {
    if (argc > 1 && std::string(argv[1]) == "--construct") {
        try {
            ConstructionConfig config;
            if (argc > 2 && std::string(argv[2]).rfind("--", 0) != 0) {
                config.method = argv[2];
            }
            for (int index = 2; index < argc; ++index) {
                const std::string option = argv[index];
                if (option == "--method" && index + 1 < argc) {
                    config.method = argv[++index];
                } else if (option == "--dataset-root" && index + 1 < argc) {
                    config.dataset_root = argv[++index];
                } else if (option == "--raw" && index + 1 < argc) {
                    config.raw_file = argv[++index];
                } else if (option == "--add" && index + 1 < argc) {
                    config.additional_file = argv[++index];
                } else if (
                    option == "--delivery-cost" && index + 1 < argc) {
                    config.delivery_cost_file = argv[++index];
                } else if (option == "--construct") {
                    continue;
                } else if (option.rfind("--", 0) == 0) {
                    throw std::invalid_argument(
                        "Unknown construction option: " + option);
                }
            }
            const ConstructionResult result = ConstructFromDataset(config);
            cout << ConstructionResultToJson(result) << endl;
            return 0;
        } catch (const std::exception &error) {
            cerr << error.what() << endl;
            return 2;
        }
    }

    auto machines = std::vector<Machine>();      // 机器列表
    auto jobs = std::vector<Job>();              // 工件列表
    auto orders = std::vector<Order>();          // 订单列表
    std::string file_path = argc > 1 ? argv[1] : "datasets/raw/Brandimarte/BrandimarteMk1.fjs";
    // cout << "file_path: " << file_path << endl;
    Init(machines, jobs, orders, file_path);    // 初始化机器、工件、订单
    auto jobList = std::vector<std::string>();   // 用于记录每个工件列表，根据订单生成
    OrderToJobList(orders, jobList);         // 将订单转换为待加工的工件列表

    if (argc > 2 && std::string(argv[2]) == "--compare-initial") {
        const InitialComparisonResult comparison = CompareInitialMethods(jobs, machines, jobList);
        size_t last_slash = file_path.find_last_of('/');
        size_t dot_pos = file_path.find_last_of('.');
        const std::string file_name = file_path.substr(last_slash + 1, dot_pos - last_slash - 1);

        cout << "instance," << file_name << endl;
        cout << "fifo_makespan," << comparison.fifo_baseline.get_fifo_total_time() << endl;
        cout << "fifo_cost," << comparison.fifo_baseline.get_fifo_earliness_tardiness_cost() << endl;
        cout << "fifo_energy," << comparison.fifo_baseline.get_fifo_energy_cost() << endl;
        cout << "method,makespan,cost,energy,combined_objective" << endl;
        for (const auto &method_metrics : comparison.methods) {
            cout << method_metrics.method_name << ","
                 << method_metrics.makespan << ","
                 << method_metrics.cost << ","
                 << method_metrics.energy << ","
                 << method_metrics.combined_objective << endl;
        }
        cout << "best_method," << comparison.best_method << endl;
        return 0;
    }

    Schedule input_schedule;                    // 输入的调度方案
    Schedule output_schedule;                   // 输出的调度方案

    // ======parameters========
    // double search_mode_param = 0.5;  // 搜索模式参数0~1，配置选择随机或者贪心
    // double random_search_strategy_param = 0.5;  // 搜索模式参数，配置选择遗传算法或者禁忌搜索
    // int max_iter_count = 30;  // 单轮优化最大迭代次数，表示每次搜索的最大迭代次数
    // int population_size = 20;  // 种群大小，表示遗传算法中种群的大小
    // int tabu_list_length = 10;  // 禁忌表长度，表示禁忌搜索算法中禁忌表的长度
    // int max_repeat_count = 20;  // 最优解最大重复次数，达到最大重复次数则退出搜索

    // double search_mode_param = 0.5;            // 搜索模式参数0~1，配置选择随机或者贪心
    // double random_search_strategy_param = 0.5; // 搜索模式参数，配置选择遗传算法或者禁忌搜索
    // int max_repeat_count = 100;                 // 最优解最大重复次数，达到最大重复次数则退出搜索
    // int max_iter_count = 30;                   // 单轮优化最大迭代次数，表示每次搜索的最大迭代次数
    // int population_size = 20;                  // 种群大小，表示遗传算法中种群的大小
    // int tabu_list_length = 50;                 // 禁忌表长度，表示禁忌搜索算法中禁忌表的长度
    

    bool force_influence_aware = false;
    int parameter_offset = 2;
    if (argc > 2 && std::string(argv[2]) == "--influence-aware") {
        force_influence_aware = true;
        parameter_offset = 3;
    }
    if (argc < parameter_offset + 6) {
        cerr << "Usage: " << argv[0] << " <instance.fjs> [--influence-aware] "
             << "<search_mode> <random_strategy> <max_repeat_count> "
             << "<max_iter_count> <population_size> <tabu_list_length>" << endl;
        return 1;
    }

    double search_mode_param = std::stod(argv[parameter_offset]);            // 搜索模式参数0~1，配置选择随机或者贪心 0.5
    double random_search_strategy_param = std::stod(argv[parameter_offset + 1]); // 搜索模式参数，配置选择遗传算法或者禁忌搜索 0.5
    int max_repeat_count = std::stoi(argv[parameter_offset + 2]); // 最优解最大重复次数，达到最大重复次数则退出搜索   100
    int max_iter_count = std::stoi(argv[parameter_offset + 3]);   // 单轮优化最大迭代次数，表示每次搜索的最大迭代次数  30
    int population_size = std::stoi(argv[parameter_offset + 4]);  // 种群大小，表示遗传算法中种群的大小  20
    int tabu_list_length = std::stoi(argv[parameter_offset + 5]); // 禁忌表长度，表示禁忌搜索算法中禁忌表的长度 25

    // ==========================

    cout << "=== Initialization ===" << endl;
    cout << "file_path: " << file_path << endl;
    cout << "search_mode_param: " << search_mode_param << endl;
    cout << "random_search_strategy_param: " << random_search_strategy_param << endl;
    cout << "max_repeat_count: " << max_repeat_count << endl;
    cout << "max_iter_count: " << max_iter_count << endl;
    cout << "population_size: " << population_size << endl;
    cout << "tabu_list_length: " << tabu_list_length << endl;
    cout << "force_influence_aware: " << force_influence_aware << endl;
    cout << "machine_count: " << machines.size() << endl;
    cout << "job_count: " << jobs.size() << endl;
    cout << "order_count: " << orders.size() << endl;
    cout << "=== Initial Solution Comparison ===" << endl;

    // if(argc > 2) {
    //     Schedule schedule0;
    //     if(strcmp(argv[2], "FIFO_EET") == 0) 
    //     {
    //         schedule0 = FIFO_EET(jobs, machines, jobList);
    //     } 
    //     else if(strcmp(argv[2], "FIFO_SPT") == 0) {
    //         schedule0 = FIFO_SPT(jobs, machines, jobList);
    //     }
    //     else if (strcmp(argv[2], "MOPNR_EET") == 0)
    //     {
    //         schedule0 = MOPNR_EET(jobs, machines, jobList);
    //     }
    //     else if (strcmp(argv[2], "MOPNR_SPT") == 0)
    //     {
    //         schedule0 = MOPNR_SPT(jobs, machines, jobList);
    //     }
    //     else if (strcmp(argv[2], "MWKR_EET") == 0)
    //     {
    //         schedule0 = MWKR_EET(jobs, machines, jobList);
    //     }
    //     else if (strcmp(argv[2], "MWKR_SPT") == 0)
    //     {
    //         schedule0 = MWKR_SPT(jobs, machines, jobList);
    //     }
    //     else
    //     {
    //         cout << "Invalid algorithm name. Please use FIFO, MOPNR, MWKR or SPT." << endl;
    //         return 1;
    //     }
    //     // schedule0.to_string();
    //     // schedule0.ToMapCode();
    //     const int ans0 = CalculateTotalTime(schedule0);
    //     cout << "Total time: " << ans0 << endl;

        
    //     // schedule0 = FIFO_EET(jobs, machines, jobList);
    //     // cout << "FIFO_EET Total time: " << CalculateTotalTime(schedule0) << endl;
    //     // schedule0 = FIFO_SPT(jobs, machines, jobList);
    //     // cout << "FIFO_SPT Total time: " << CalculateTotalTime(schedule0) << endl;
    //     // schedule0 = MOPNR_EET(jobs, machines, jobList);
    //     // cout << "MOPNR_EET Total time: " << CalculateTotalTime(schedule0) << endl;
    //     // schedule0 = MOPNR_SPT(jobs, machines, jobList);
    //     // cout << "MOPNR_SPT Total time: " << CalculateTotalTime(schedule0) << endl;
    //     // schedule0 = MWKR_EET(jobs, machines, jobList);
    //     // cout << "MWKR_EET Total time: " << CalculateTotalTime(schedule0) << endl;
    //     // schedule0 = MWKR_SPT(jobs, machines, jobList);
    //     // cout << "MWKR_SPT Total time: " << CalculateTotalTime(schedule0) << endl;
    //     // cout << endl;
    //     return 0;
    // }

    cout << "=== InfluenceAware Initial Solution ===" << endl;

    const InitialComparisonResult initial_comparison = CompareInitialMethods(jobs, machines, jobList);
    Schedule fifo_baseline = initial_comparison.fifo_baseline;
    Schedule schedule0;
    std::string initial_method_name;
    if (force_influence_aware) {
        schedule0 = InfluenceAwareConstruct(jobs, machines, jobList);
        schedule0.set_fifo_total_time(fifo_baseline.get_fifo_total_time());
        schedule0.set_fifo_earliness_tardiness_cost(
            fifo_baseline.get_fifo_earliness_tardiness_cost());
        schedule0.set_fifo_energy_cost(fifo_baseline.get_fifo_energy_cost());
        CalculateCombinedObjective(schedule0);
        initial_method_name = "InfluenceAware";
    } else {
        schedule0 = initial_comparison.best_schedule;
        initial_method_name = initial_comparison.best_method;
    }

    const int ans0 = CalculateTotalTime(schedule0);
    cout << "Selected method: " << initial_method_name << endl;
    cout << "Initial Total time: " << ans0 << endl;
    cout << "Initial earliness tardiness cost: " << schedule0.get_total_earliness_tardiness_cost() << endl;
    cout << "Initial energy cost: " << schedule0.get_total_energy_cost() << endl;
    cout << "FIFO baseline Total time: " << fifo_baseline.get_fifo_total_time() << endl;
    cout << "FIFO baseline Total earliness tardiness cost: " << fifo_baseline.get_fifo_earliness_tardiness_cost() << endl;
    cout << "FIFO baseline Total energy cost: " << fifo_baseline.get_fifo_energy_cost() << endl;
    cout << "Initial Combined objective: " << schedule0.get_combined_objective() << endl;

    Schedule temp_schedule;
    input_schedule = schedule0;
    output_schedule = schedule0;

    int search_time = time(nullptr), count = 0, repeat_count =0;
    Schedule start_schedule = input_schedule;
    srand(time(nullptr));
    
    cout << "=== Optimization Started ===" << endl;
    cout << "Start time: " << search_time << endl;
    cout << "============================" << endl;
    
    while (CheckStopFlag(search_time, count, repeat_count, max_repeat_count)) {
        double random_num = static_cast<double>(std::rand()) / RAND_MAX;
        
        if (random_num < search_mode_param) {
            int time_start = time(nullptr);
            temp_schedule = RandomSearch(input_schedule, jobs, machines, jobList, random_search_strategy_param, repeat_count, max_repeat_count, max_iter_count, tabu_list_length, population_size);
            int time_cost = time(nullptr) - time_start;
            
            if (temp_schedule.get_combined_objective()<output_schedule.get_combined_objective()) {
                output_schedule = temp_schedule;
                input_schedule = temp_schedule;
                cout << "[Iter " << count << "] Random Search improved! Time: " << time_cost << "s | TotalTime: " << output_schedule.get_TotalTime() << " | Cost: " << output_schedule.get_total_earliness_tardiness_cost() << " | Energy: " << output_schedule.get_total_energy_cost() << " | HV: " << CalculateHV(output_schedule) << " | CO: " << output_schedule.get_combined_objective() << endl;
            } else {
                cout << "[Iter " << count << "] Random Search no improvement. Time: " << time_cost << "s" << endl;
            }
        } else {
            int time_start = time(nullptr);
            temp_schedule = GreedySearch(input_schedule, jobs, jobList, max_iter_count, machines);
            int time_cost = time(nullptr) - time_start;
            
            if (temp_schedule.get_combined_objective()<output_schedule.get_combined_objective()) {
                output_schedule = temp_schedule;
                input_schedule = temp_schedule;
                cout << "[Iter " << count << "] Greedy Search improved! Time: " << time_cost << "s | TotalTime: " << output_schedule.get_TotalTime() << " | Cost: " << output_schedule.get_total_earliness_tardiness_cost() << " | Energy: " << output_schedule.get_total_energy_cost() << " | HV: " << CalculateHV(output_schedule) << " | CO: " << output_schedule.get_combined_objective() << endl;
            }
            else {
                cout << "[Iter " << count << "] Greedy Search no improvement, trying Random... ";
                time_start = time(nullptr);
                temp_schedule = RandomSearch(input_schedule, jobs, machines, jobList, random_search_strategy_param, repeat_count, max_repeat_count, max_iter_count, tabu_list_length, population_size);
                time_cost = time(nullptr) - time_start;
                
                if (temp_schedule.get_combined_objective()<output_schedule.get_combined_objective()) {
                    output_schedule = temp_schedule;
                    input_schedule = temp_schedule;
                    cout << "improved! Time: " << time_cost << "s | TotalTime: " << output_schedule.get_TotalTime() << " | CO: " << output_schedule.get_combined_objective() << endl;
                } else {
                    cout << "no improvement. Time: " << time_cost << "s" << endl;
                }
            }
        }

        if (output_schedule.get_combined_objective()<=start_schedule.get_combined_objective()) {
            if (output_schedule.get_combined_objective() < start_schedule.get_combined_objective()) {
                repeat_count = 1;
            } else {
                repeat_count++;
            }
        } else {
            repeat_count++;
        }
        
        count++;
        start_schedule = output_schedule;
        
        if (count % 10 == 0) {
            int elapsed = time(nullptr) - search_time;
            cout << "[Progress] Iteration: " << count << " | Repeat: " << repeat_count << "/" << max_repeat_count << " | Elapsed: " << elapsed << "s" << endl;
        }
    }

    // output_schedule.to_string();
    // output_schedule.ToMapCode();
    const int ans1 = CalculateTotalTime(output_schedule);
    double hv = CalculateHV(output_schedule);
    int total_time = time(nullptr) - search_time;
    
    cout << "=== Optimization Completed ===" << endl;
    cout << "Total iterations: " << count << endl;
    cout << "Total time elapsed: " << total_time << "s" << endl;
    cout << "Final TotalTime: " << ans1 << endl;
    cout << "Final EarlinessTardinessCost: " << output_schedule.get_total_earliness_tardiness_cost() << endl;
    cout << "Final EnergyCost: " << output_schedule.get_total_energy_cost() << endl;
    cout << "Final HV: " << hv << endl;
    cout << "Final Combined Objective: " << output_schedule.get_combined_objective() << endl;
    cout << "=== FIFO Baseline ===" << endl;
    cout << "FIFO TotalTime: " << fifo_baseline.get_fifo_total_time() << endl;
    cout << "FIFO EarlinessTardinessCost: " << fifo_baseline.get_fifo_earliness_tardiness_cost() << endl;
    cout << "FIFO EnergyCost: " << fifo_baseline.get_fifo_energy_cost() << endl;
    cout << "=== Improvement ===" << endl;
    cout << "Time improvement: " << fifo_baseline.get_fifo_total_time() - ans1 << " (" << (1.0 - ans1 * 1.0 / fifo_baseline.get_fifo_total_time()) * 100 << "%)" << endl;
    cout << "Cost improvement: " << fifo_baseline.get_fifo_earliness_tardiness_cost() - output_schedule.get_total_earliness_tardiness_cost() << " (" << (1.0 - output_schedule.get_total_earliness_tardiness_cost() * 1.0 / fifo_baseline.get_fifo_earliness_tardiness_cost()) * 100 << "%)" << endl;
    cout << "Energy improvement: " << fifo_baseline.get_fifo_energy_cost() - output_schedule.get_total_energy_cost() << " (" << (1.0 - output_schedule.get_total_energy_cost() * 1.0 / fifo_baseline.get_fifo_energy_cost()) * 100 << "%)" << endl;

    PrintScheduleDetails(output_schedule, jobs);

    size_t last_slash = file_path.find_last_of('/');
    size_t dot_pos = file_path.find_last_of('.');
    std::string file_name = file_path.substr(last_slash + 1, dot_pos - last_slash - 1);

    cout << file_name << ","
         << ans1 << ","
         << output_schedule.get_total_earliness_tardiness_cost() << ","
         << output_schedule.get_total_energy_cost() << ","
         << fifo_baseline.get_fifo_total_time() << ","
         << fifo_baseline.get_fifo_earliness_tardiness_cost() << ","
         << fifo_baseline.get_fifo_energy_cost() << ","
         << hv << endl;

    return 0;
}

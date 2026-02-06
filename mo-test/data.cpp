#include<bits/stdc++.h>
#include"nlohmann/json.hpp"

using namespace std;
using json = nlohmann::json;

random_device rd;
mt19937 gen(rd());
uniform_real_distribution<double> dist(0.0, 1.0);

int N[5];
double D[5], T[5];
double p_tp[] = {0, 0.1, 0.4, 0.3, 0.2};

double task_l[] = {10, 100, 1000}, task_b[] = {1, 50, 2 * 1024, 20 * 1024};
double p_task_b[] = {0.3, 0.4, 0.2, 0.1};

string tostring(int x, int len) {
    string res(len, '0');
    int i = len;
    while(x) {
        res[--i] = x % 10 + '0';
        x /= 10;
    }
    return res;
}

struct R;
struct Net;

struct Task {
    int index;
    int priority;
    bool finish;
    double max_latency, min_bandwidth;
    double now_l;
    vector<pair<R*, Net*>> edge;
    Task() {
        rebuild();
    }
    void rebuild() {
        max_latency = task_l[rand() % 3];
        double rd = dist(gen), sum = 0;
        for(int i = 0; i < 4; i++) {
            sum += p_task_b[i];
            if(rd < sum) {
                min_bandwidth = task_b[i];
                break;
            }
        }
        now_l = 0;
        finish = 1;
    }
    string get_id() {
        return tostring(index, 8);
    }
};

struct R {
    int index;
    vector<Net*> v_net;
    int cap, cap_net;
    int used_cap;
    bool used, is_gateway;
    double acost;
    R(bool is_gateway = false) : is_gateway(is_gateway) {
        // cap = dist(gen) * 2 + 2;
        // cap_net = dist(gen) * 2 + 2;
        cap = 3;
        cap_net = 3;
        used = (dist(gen) > 1. / 20);
        used_cap = 0;
        acost = 10 * dist(gen);
    }
    string get_id() {
        return tostring(index, 4);
    }
};

struct Net {
    int index;
    int tp, num_r;
    vector<R*> v_r;
    map<R*, double> max_out;
    double now_bw;
    Net() {
        now_bw = 0;
    }
    void push_r(R* r) {
        v_r.push_back(r);
        r->v_net.push_back(this);
        max_out.insert({r, 0});
    }
    bool check(R* r, Task* task) {
        double bw = task->min_bandwidth;
        bool ok = now_bw + max(0., bw - max_out[r]) < D[tp];
        if(!ok) {
            cerr << "error: bw" << endl;
            cerr << "now_bw = " << now_bw << "  task_bw = " << bw << "  D = " << D[tp] << endl;
            return ok;
        }
        ok &= (r->used_cap + 1 <= r->cap);
        if(!ok) {
            cerr << "error: cap" << endl;
            cerr << "used: " << r->used_cap << " cap: " << r->cap << endl;
            return ok;
        }
        ok &= (task->now_l + T[tp] <= task->max_latency);
        if(!ok) {
            cerr << "error: time" << endl;
            return ok;
        }
        return ok;
    }
    void modify(R* r, Task* task) {
        double bw = task->min_bandwidth;
        now_bw += max(0., bw - max_out[r]);
        max_out[r] = max(max_out[r], bw);
        r->used_cap++;
        task->now_l += T[tp];
    }
    string get_id() {
        return "w" + tostring(index, 5);
    }
};

template<class T>
void get_rand_rk(vector<T> &v, int sz) {
    v.resize(sz);
    iota(v.begin(), v.end(), 0);
    shuffle(v.begin(), v.end(), gen);
}

template<class T>
void get_determined_sum(T &v, double sum = 1) {
    double s = 0;
    for(auto &t : v) {
        t = dist(gen);
        s += t;
    }
    for(auto &t : v) {
        t = t / s * sum;
    }
}

int main() {
    json j;

    freopen("data10.in", "w", stdout);
    srand(time(0));

    vector<int> rk;
    vector<double> w(3);

    get_rand_rk(rk, 3);
    w[rk[0]] = dist(gen);
    w[rk[1]] = dist(gen) * (1 - w[rk[0]]);
    w[rk[2]] = 1 - w[rk[0]] - w[rk[1]];

    D[1] = 300 * 1024 + dist(gen) * 800000;
    D[3] = 100 * 1024;
    D[2] = 8 * 1024;
    D[4] = 2 * 1024;

    T[1] = T[4] = 100;
    T[3] = 10;
    T[2] = 2;

    N[4] = 1000;
    N[2] = N[3] = 128;
    N[1] = 32;

    vector<Net> v_net;
    vector<R> v_r;
    set<pair<R*, R*>> st_e;
    v_net.reserve(1000);
    v_r.reserve(2000);
    int n_r = 1000 - dist(gen) * 50;
    while(n_r >= 0) {
        v_net.emplace_back();
        auto &net = v_net.back();
        double rd = dist(gen), sum = 0;
        for(int i = 1; i <= 4; i++) {
            sum += p_tp[i];
            if(rd < sum) {
                net.tp = i;
                break;
            }
        }
        net.tp = rand() % 4 + 1;
        net.num_r = max(3., min(1. * N[net.tp], N[net.tp] * 0.1 + pow(dist(gen), 2) * pow(dist(gen), 2) * N[net.tp] * 0.9));
        cerr << "net.num_r = " << net.num_r << endl;
        // cout << "net.num_r = " << net.num_r << endl;
        n_r -= net.num_r;
    }
    cerr << "ok1  n_r = " << n_r << "(<0right)" << endl;

    //网关结点联通
    vector<vector<Net*>> dsu;
    for(auto &net : v_net)
        dsu.push_back({&net});
    while(dsu.size() > 1) {
        sort(dsu.begin(), dsu.end(), [&](vector<Net*> &u, vector<Net*> &v) {
            int su = 0, sv = 0;
            for(auto &net : u)
                su += net->v_r.size();
            for(auto &net : v)
                sv += net->v_r.size();
            return su * v.size() < sv * u.size();
        });
        // int i = rand() % dsu.size();
        // int j = rand() % dsu.size();
        int i = 0, j = 1;
        // cerr << "i = " << i << "  j = " << j << endl;
        if(i == j) continue;
        auto pick = [&](int id) -> int {
            shuffle(dsu[id].begin(), dsu[id].end(), gen);
            for(int i = 0; i < dsu[id].size(); i++)
                if(dsu[id][i]->v_r.size() < 2)
                    return i;
            return -1;
        };
        int x = pick(i), y = pick(j);
        if(x == -1 || y == -1) {
            continue;
        }
        if(dsu[i].size() < dsu[j].size()) {
            swap(dsu[i], dsu[j]);
            swap(x, y);
        }
        v_r.emplace_back(true);
        dsu[i][x]->push_r(&v_r.back());
        dsu[j][y]->push_r(&v_r.back());
        for(auto &net : dsu[j])
            dsu[i].push_back(net);
        swap(dsu[j], dsu.back());
        dsu.pop_back();
        if(v_r.back().v_net.size() < v_r.back().cap_net && dist(gen) < 0.1) {
            int i = rand() % dsu.size();
            int x = rand() % dsu[i].size();
            if(dsu[i][x]->max_out.count(&v_r.back()))
                continue;
            dsu[i][x]->push_r(&v_r.back());
        }
    }
    cerr << "ok2" << endl;
    //加net.size() / 10个网关
    for(int i = v_net.size() / 10; i >= 1; i--) {
        int x = rand() % v_net.size();
        int y = rand() % v_net.size();
        if(x == y) continue;
        if(v_net[x].v_r.size() >= 2 || v_net[y].v_r.size() >= 2)
            continue;
        v_r.emplace_back(true);
        v_net[x].push_r(&v_r.back());
        v_net[y].push_r(&v_r.back());
    }
    cerr << "ok3" << endl;
    //非网关节点
    for(auto &net : v_net) {
        while(net.v_r.size() < net.num_r) {
            v_r.emplace_back(false);
            net.push_r(&v_r.back());
        }
        if(net.tp <= 3) {
            for(int i = 0; i < net.v_r.size(); i++) {
                for(int j = i + 1; j < net.v_r.size(); j++) {
                    st_e.insert({net.v_r[i], net.v_r[j]});
                    st_e.insert({net.v_r[j], net.v_r[i]});
                }
            }
        } else {
            shuffle(net.v_r.begin(), net.v_r.end(), gen);
            auto get_tp = [&](int i) -> int {
                if(i <= net.v_r.size() / 3) return 0;
                if(i <= net.v_r.size() * 2 / 3) return 1;
                return 2;
            };
            for(int i = 0; i < net.v_r.size(); i++) {
                for(int j = i + 1; j < net.v_r.size(); j++) {
                    int ti = get_tp(i), tj = get_tp(j);
                    if(tj - ti == 2) continue;
                    if(ti == tj) {
                        if(dist(gen) < 0.2) {
                            st_e.insert({net.v_r[i], net.v_r[j]});
                            st_e.insert({net.v_r[j], net.v_r[i]});
                        }
                    } else {
                        st_e.insert({net.v_r[i], net.v_r[j]});
                        st_e.insert({net.v_r[j], net.v_r[i]});
                    }
                }
            }
        }
    }
    cerr << "ok4" << endl;

    //每个网络至少一资源
    for(auto &nt : v_net) {
        int t = rand() % nt.num_r;
        auto r = nt.max_out.begin();
        while(t--)
            r = next(r);
        r->first->used = false;
    }

    for(int i = 0; i < v_net.size(); i++)
        v_net[i].index = i;
    for(int i = 0; i < v_r.size(); i++)
        v_r[i].index = i;

    //边整理
    map<R*, vector<R*>> to;
    for(auto [u, v] : st_e)
        to[u].push_back(v);
    cerr << "ok5" << endl;
    
    //任务
    cerr << "v_net.size = " << v_net.size() << endl;
    cerr << "v_r.size = " << v_r.size() << endl;
    vector<Task> v_task(20);
    vector<int> cal_times(20);
    for(int i = 0; i < 20; i++) {
        cerr << "i = " << i << endl;
        cal_times[i]++;
        if(cal_times[i] % 20 == 0) {
            v_task[i].rebuild();
            cerr << "rebuild task" << i << endl;
        }
        // cerr << "task[" << i << "]" << endl;
        auto &task = v_task[i];
        if(dist(gen) < 0.2)
            task.priority = 3;
        else if(dist(gen) < 0.5)
            task.priority = 2;
        else
            task.priority = 1;
        set<R*> st_pass_r;
        int cnt = 0;
        while(1) {
            cnt++;
            if(cnt > 50)
                break;
            auto &r = v_r[rand() % v_r.size()];
            auto &net = r.v_net[rand() % r.v_net.size()];
            // cerr << "get r" << r.get_id() << " w" << net->get_id() << endl;
            if(!net->check(&r, &task)) {
                cerr << "error1: check net" << endl;
                continue;
            }
            st_pass_r.insert(&r);
            task.edge.emplace_back(&r, net);
            break;
        }
        if(cnt > 50) {
            task.edge.clear();
            task.now_l = 0;
            i--;
            cerr << "error: type1" << endl;
            continue;
        }
        cnt = 0;
        while(1) {
            if(task.edge.size() >= 2 + dist(gen) * 15)
                break;
            cnt++;
            if(cnt > 50)
                break;
            auto &[last_r, last_net] = task.edge.back();
            auto &r = to[last_r][rand() % to[last_r].size()];
            auto &net = r->v_net[rand() % r->v_net.size()];
            // cerr << "*get r" << r->get_id() << " w" << net->get_id() << endl;
            if(!net->check(r, &task)) {
                cerr << "error2: check net" << endl;
                continue;
            }
            if(st_pass_r.count(r)) {
                cerr << "error2: count" << endl;
                continue;
            }
            last_net->modify(last_r, &task);
            task.edge.emplace_back(r, net);
            st_pass_r.insert(r);
            cnt = 0;
        }
        if(task.edge.size() <= 2) {
            task.edge.clear();
            task.now_l = 0;
            i--;
            cerr << "error: type2" << endl;
            continue;
        }
        for(auto &[r, net] : task.edge)
            task.finish &= r->used;
    }
    // for(int i = 0; i < v_task.size(); i++) {
    //     if(!v_task[i].edge.size()) {
    //         v_task.resize(i);
    //         break;
    //     }
    // }
    for(int i = 0; i < v_task.size(); i++) {
        if(!v_task[i].edge.size()) {
            auto &task = v_task[i];
            if(dist(gen) < 0.2)
                task.priority = 3;
            else if(dist(gen) < 0.5)
                task.priority = 2;
            else
                task.priority = 1;
            task.finish = false;
            task.edge.resize(2);
            task.edge[0].first = &v_r[rand() % v_r.size()];
            while(1) {
                task.edge[1].first = &v_r[rand() % v_r.size()];
                if(task.edge[0].first != task.edge[1].first)
                    break;
            }
        }
    }
    cerr << "ok6" << endl;
    

    //now_bandwidth, num_finish
    int num_finish = 0;
    for(auto &net : v_net) {
        net.now_bw = 0;
        net.max_out.clear();
    }
    for(auto &task : v_task) {
        if(!task.finish)
            continue;
        num_finish++;
        for(int i = 0; i + 1 < task.edge.size(); i++) {
            auto &[r, net] = task.edge[i];
            net->now_bw += max(0., task.min_bandwidth - net->max_out[r]);
            net->max_out[r] = max(net->max_out[r], task.min_bandwidth);
        }
    }
    cerr << "ok7" << endl;

    //num_z
    int num_z = 0;
    for(auto &r : v_r) {
        if(!r.used)
            num_z++;
    }

    for(int i = 0; i < v_task.size(); i++)
        v_task[i].index = i;


    // cout << w[0] << ' ' << w[1] << ' ' << w[2] << endl;
    // cout << endl;
    j["w1"] = w[0];
    j["w2"] = w[1];
    j["w3"] = w[2];
    
    // cout << v_net.size() << endl;
    json &j_net = j["list_wangluo"];
    for(auto &net : v_net) {
        json item;
        net.num_r = 0;
        for(auto &r : net.v_r) {
            if(r->used)
                net.num_r++;
        }
        // cout << net.num_r << endl;
        item["num_shebei"] = net.num_r;
        json& j_r = item["list_shebei"];
        for(auto &r : net.v_r) {
            if(!r->used) continue;
            json item;
            // cout << r->get_id() << ' ' << "name" + r->get_id() << ' ';
            // cout << (r->is_gateway ? "1" : "0") << ' ' << r->cap << endl;
            item["id"] = r->get_id();
            item["name"] = "name" + r->get_id();
            item["is_gateway"] = r->is_gateway;
            item["max_concurrent_tasks"] = r->cap;
            j_r.push_back(item);
        }
        // cout << T[net.tp] << endl;
        item["latency"] = T[net.tp];
        // cout << D[net.tp] << endl;
        item["bandwidth"] = D[net.tp];
        vector<pair<R*, R*>> e;
        for(auto &[u, v] : st_e) {
            if(u > v)
                continue;
            if(!u->used || !v->used)
                continue;
            if(!net.max_out.count(u) || ! net.max_out.count(v))
                continue;
            e.emplace_back(u, v);
        }
        // cout << e.size() << endl;
        json &j_e = item["list_normal_bian"];
        j_e = json::array();
        for(auto &[u, v] : e) {
            // cout << u->get_id() << ' ' << v->get_id() << endl;
            json item;
            item["source_id"] = u->get_id();
            item["target_id"] = v->get_id();
            j_e.push_back(item);
        }
        // cout << net.get_id() << endl;
        item["id"] = net.get_id();
        // cout << net.now_bw << endl;
        item["used_bandwidth"] = net.now_bw;
        // item["now_bandwidth"] = net.now_bw;
        j_net.push_back(item);
    }
    // cout << endl;

    // cout << num_z << endl;
    json &j_r = j["list_ziyuan"];
    for(auto &r : v_r) {
        if(r.used) continue;
        json item;
        // cout << r.get_id() << ' ' << r.v_net.size() << ' ';
        item["id"] = r.get_id();
        item["name"] = "name" + r.get_id();
        json &j_net = item["list_wangluo"];
        for(auto &net : r.v_net) {
            json item;
            // cout << net->get_id() << ' ';
            item = net->get_id();
            j_net.push_back(item);
        }
        // cout << (r.is_gateway ? "1" : "0") << ' ' << r.acost << ' ';
        item["acost"] = r.acost;
        vector<R*> e;
        for(auto &[u, v] : st_e) {
            if(u > v)
                continue;
            if(u == &r)
                e.emplace_back(v);
            else if(v == &r)
                e.emplace_back(u);
        }
        // cout << e.size() << ' ';
        json &j_e = item["list_normal_bian"];
        for(auto &r2 : e) {
            json item;
            // cout << r->get_id() << ' ';
            item["source_id"] = r.get_id();
            item["target_id"] = r2->get_id();
            j_e.push_back(item);
        }
        // cout << r.cap << endl;
        item["max_concurrent_tasks"] = r.cap;
        j_r.push_back(item);
    }
    // cout << endl;

    // cout << v_task.size() << endl;
    json &j_t = j["list_renwu"];
    for(auto &task : v_task) {
        json item;
        // cout << task.priority << ' ';
        item["priority"] = task.priority;
        // cout << task.edge.begin()->first->get_id() << ' ' << task.edge.back().first->get_id() << ' ';
        item["source_id"] = task.edge.begin()->first->get_id();
        item["target_id"] = task.edge.back().first->get_id();
        // cout << task.max_latency << ' ' << task.min_bandwidth << ' ';
        item["max_latency"] = task.max_latency;
        item["min_bandwidth"] = task.min_bandwidth;
        // cout << "name" + task.get_id() << ' ' << task.get_id() << endl;
        item["name"] = "name" + task.get_id();
        item["id"] = task.get_id();
        
        if(task.finish) {
            item["finish"] = true;
            json &j_b = item["list_bian"];
            // cout << task.get_id() << endl;
            // cout << task.edge.size() - 1 << endl;
            for(int i = 0; i + 1 < task.edge.size(); i++){
                json item;
                auto &[r1, net1] = task.edge[i];
                auto &[r2, net2] = task.edge[i + 1];
                // cout << r1->get_id() << ' ' << net1->get_id() << ' '
                //      << r2->get_id() << ' ' << net2->get_id() <<endl;
                item["source_pid"] = r1->get_id();
                item["source_wid"] = net1->get_id();
                item["target_pid"] = r2->get_id();
                item["target_wid"] = net2->get_id();
                j_b.push_back(item);
            }

        } else {
            item["finish"] = false;
            item["list_bian"] = nullptr;
        }

        j_t.push_back(item);
    }
    // cout << endl;
    
    cout << j.dump(4) << endl;
/*

1.1 w1 w2 w3
1.3 num, {WangLuo(
        num_sheBei,
        {SheBei(id, name, is_gateway, capcity)},
        latency,
        bandwidth,
        num_normalBian,
        {normalBian(start, end)},
        id,
        now_bandwidth,
    )}
1.4 num, {ZiYuan(id, num_wangLuo, {id_wangLuo}, is_gateway, acost, num_edge, {id_platform}, capacity)}
1.2 num, {RenWu(priority, start, end, max_latency, min_bandwidth, name, id)}
1.5 num, {RenWu(id, num_bian, {bian(start, start_net, end, end_net)})}

*/
    return 0;
}
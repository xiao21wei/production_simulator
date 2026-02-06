import os
import sys
import torch
import pandas as pd
import numpy as np
from model_predict.conf.MetroPT_Configs import Config
from model_predict.models.model import Base_Model

# Ensure the current directory is in the python path
sys.path.append(os.getcwd())

# Global caches for backward compatibility/helper usage
_MODEL_INSTANCE = None
_DATA_CACHE = {}

def load_model(device=None, model_path=None):
    """
    加载异常检测模型。
    """
    if device is None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
    configs = Config()
    # 确保配置参数与训练设置一致
    configs.window_size = 100
    configs.time_step = 20
    configs.prediction_horizon = 20
    
    if model_path is None:
        model_path = 'model_predict/models/metropt_model.pth'
        
    model = Base_Model(configs, device)
    
    if os.path.exists(model_path):
        try:
            # 尝试加载 state_dict
            checkpoint = torch.load(model_path, map_location=device)
            if isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
                 model.load_state_dict(checkpoint['state_dict'])
            elif isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                 model.load_state_dict(checkpoint['model_state_dict']) 
            else:
                 # 尝试作为直接的 state dict 或完整模型加载
                 try:
                    model.load_state_dict(checkpoint)
                 except:
                    pass
        except Exception as e:
            print(f"警告: 加载模型 state_dict 出错: {e}")
    else:
        raise FileNotFoundError(f"找不到模型文件: {model_path}")
        
    model.to(device)
    model.eval()
    return model

def load_data(machine_id):
    """
    加载特定机器的 CSV 数据。
    """
    file_path = f'model_predict/data/machines/machine_{machine_id}.csv'
    if not os.path.exists(file_path):
        return None
        
    df = pd.read_csv(file_path)
    return df

def get_history_window(df, t, window_len=100):
    """
    提取时刻 t 之前的长度为 window_len 的历史窗口。
    返回形状为 (window_len, features) 的 numpy 数组。
    """
    
    end_row_idx = 100 + t * 2
    start_row_idx = end_row_idx - window_len
    
    if start_row_idx < 0:
        raise ValueError(f"时刻 t={t} 太早了。需要至少 {window_len} 行历史数据。")
    
    if end_row_idx > len(df):
        raise ValueError(f"时刻 t={t} 超出了数据集范围。")
        
    # 提取窗口数据
    cols_to_exclude = ['timestamp', 'label']
    valid_cols = [c for c in df.columns if c not in cols_to_exclude]
    
    window_data = df.iloc[start_row_idx:end_row_idx][valid_cols].to_numpy()
    
    if window_data.shape[0] != window_len:
        raise ValueError(f"提取的窗口大小为 {window_data.shape[0]}，预期为 {window_len}。")
        
    return window_data

def predict(model, window_data):
    """
    对单个数据窗口运行推理。
    """
    # 准备 tensor
    x_tensor = torch.from_numpy(window_data).float() # (100, 15)
    x_tensor = x_tensor.unsqueeze(0) # (1, 100, 15)
    x_tensor = x_tensor.permute(0, 2, 1) # (1, 15, 100) -> (Batch, Channel, Length)
    
    device = next(model.parameters()).device
    
    with torch.no_grad():
        output = model(x_tensor.to(device))
        prob = output.item()
        
    return prob

def get_label(df, t, t1):
    """
    获取过去第 t1 个时刻的标签 (t - t1)。
    """
    target_t = t - t1
    start_row_idx = 100 + target_t * 2
    
    # 边界检查
    if start_row_idx < 0:
        start_row_idx = max(0, start_row_idx)
        if start_row_idx < 0: return 0 

    if start_row_idx >= len(df):
        return 0
        
    end_row_idx = start_row_idx + 2
    rows = df.iloc[start_row_idx:end_row_idx]
    
    if 'label' not in rows.columns:
        raise ValueError("数据集中未找到标签列。")
        
    labels = rows['label'].values
    if np.sum(labels) >= 1:
        return 1
    else:
        return 0

# --- 用于向后兼容的封装函数 ---

def _get_cached_model():
    global _MODEL_INSTANCE
    if _MODEL_INSTANCE is None:
        _MODEL_INSTANCE = load_model()
    return _MODEL_INSTANCE

def _get_cached_data(machine_id):
    global _DATA_CACHE
    if machine_id not in _DATA_CACHE:
        _DATA_CACHE[machine_id] = load_data(machine_id)
    return _DATA_CACHE[machine_id]

def predict_anomaly_prob(t, machine_id):
    """
    使用缓存的模型和数据进行预测。
    """
    model = _get_cached_model()
    df = _get_cached_data(machine_id)
    window_data = get_history_window(df, t, window_len=100)
    return predict(model, window_data)

def get_past_label(t, machine_id, t1):
    """
    使用缓存的数据获取历史标签。
    """
    df = _get_cached_data(machine_id)
    return get_label(df, t, t1)

if __name__ == "__main__":
    # 测试用例
    test_t = 0          # 时刻: 0 1 2 ...
    test_machine = 0    # 机器id: 0, 1, 2, 3, 4
    
    print(f"正在测试：时刻 t={test_t}, 机器 ID={test_machine}")
    
    # 测试功能性用法
    print("正在测试底层功能函数...")
    model = load_model()            # 加载模型
    df = load_data(test_machine)    # 加载数据集
    win = get_history_window(df, test_t) # 加载对应时刻的历史50个窗口
    p = predict(model, win)              # 预测未来10个时刻的窗口发生异常的概率
    l = get_label(df, test_t, 10)        # 获取某个机器，过去第10个时刻的标签：0：正常，1：异常
    print(f"概率: {p:.4f}, 标签 (t-10): {l}")
    
    # 测试封装后的用法
    print("\n正在测试封装后的工具函数...")
    try:
        prob = predict_anomaly_prob(test_t, test_machine)
        print(f"预测异常概率: {prob:.4f}")
    except Exception as e:
        print(f"预测失败: {e}")
        
    try:
        past_label = get_past_label(test_t, test_machine, 10)
        print(f"过去第 10 个时刻的标签 (t-10): {past_label}")
    except Exception as e:
        print(f"获取标签失败: {e}")
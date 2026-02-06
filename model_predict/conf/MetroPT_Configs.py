class Config(object):
    def __init__(self):
        # datasets
        self.dataset = 'MetroPT'
        self.method = 'samplemix'
        self.description = 'no_mixup'
    
        self.input_channels = 15
        self.window_size = 100
        self.time_step = 20
        self.dropout = 0.45

        self.cnn_layer1_filters = 32
        self.cnn_kernel_size = 4         
        self.cnn_pool_kernel_size = 4   
        self.cnn_pool_stride = 4       

        self.num_lstm_layers = 2    
        self.lstm1_hidden_size = 64
        self.lstm2_hidden_size = 32   
        self.lstm_dropout = 0.2

        self.projection_intermediate_dim = 128

        self.num_epoch = 300
        self.patience = 40

        self.beta1 = 0.9
        self.beta2 = 0.99
        self.lr = 5e-4
        self.weight = 5e-4

        self.drop_last = True
        self.batch_size = 512
        self.trend_rate = 1
        self.rate = 0
        self.cut_rate = 9

        # generate mixed samples
        self.mixed_samples = False
        self.mixed_method = 'beta' 
        self.beta = 0.5
        self.target_num = 10001

        # 故障预测参数
        self.prediction_horizon = 20  # 预测未来 N 个时间步是否发生故障

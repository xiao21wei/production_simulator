from torch import nn
import torch

class Base_Model(nn.Module):
    def __init__(self, configs, device):
        super(Base_Model, self).__init__()
        self.input_channels = configs.input_channels       # Number of channels in the multivariate time series
        self.window_size = configs.window_size             # Input time window size
        self.device = device

        # CNN Feature Extractor
        self.cnn_layer1_filters = configs.cnn_layer1_filters
        self.cnn_kernel_size = configs.cnn_kernel_size
        self.cnn_pool_kernel_size = configs.cnn_pool_kernel_size
        self.cnn_pool_stride = configs.cnn_pool_stride 

        self.cnn_feature_extractor = nn.Sequential(
            nn.Conv1d(
                in_channels=self.input_channels,
                out_channels=self.cnn_layer1_filters,
                kernel_size=self.cnn_kernel_size,
                padding=(self.cnn_kernel_size // 2) 
            ),
            nn.BatchNorm1d(self.cnn_layer1_filters), 
            nn.ReLU(),
            nn.MaxPool1d(
                kernel_size=self.cnn_pool_kernel_size,
                stride=self.cnn_pool_stride
            ),
            nn.Dropout(configs.dropout) 
        )

        _seq_len_after_cnn = (self.window_size - self.cnn_pool_kernel_size) // self.cnn_pool_stride + 1

        # LSTM Layers
        self.lstm1_hidden_size = configs.lstm1_hidden_size
        self.lstm2_hidden_size = configs.lstm2_hidden_size
        self.lstm_dropout = configs.lstm_dropout

        self.lstm1 = nn.LSTM(
            input_size=self.cnn_layer1_filters,
            hidden_size=self.lstm1_hidden_size,
            num_layers=1, 
            batch_first=True 
        )

        self.lstm2 = nn.LSTM(
            input_size=self.lstm1_hidden_size,
            hidden_size=self.lstm2_hidden_size,
            num_layers=1,
            batch_first=True
        )

        # Regression Head
        self.projection_intermediate_dim = configs.projection_intermediate_dim
        self.regression_head = nn.Sequential(
            nn.Linear(self.lstm2_hidden_size, self.projection_intermediate_dim),
            nn.BatchNorm1d(self.projection_intermediate_dim), 
            nn.ReLU(),
            nn.Dropout(configs.dropout), 
            nn.Linear(self.projection_intermediate_dim, 1),
            nn.Sigmoid()
        )

    def forward(self, x_in):
        if torch.isnan(x_in).any():
            print('Input tensor contains nan')
            x_in = torch.nan_to_num(x_in)

        cnn_features = self.cnn_feature_extractor(x_in)
        lstm_input = cnn_features.permute(0, 2, 1)
        lstm1_out, (h_n1, c_n1) = self.lstm1(lstm_input)
        if self.lstm_dropout > 0:
           lstm1_out = nn.functional.dropout(lstm1_out, p=self.lstm_dropout, training=self.training)
        lstm2_out, (h_n2, c_n2) = self.lstm2(lstm1_out)
        last_lstm_sequence_output = lstm2_out[:, -1, :] 
        anomaly_prob = self.regression_head(last_lstm_sequence_output) 

        return anomaly_prob
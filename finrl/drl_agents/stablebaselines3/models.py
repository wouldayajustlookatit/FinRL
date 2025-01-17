# common library
import pandas as pd
import numpy as np
import time
import gym

from finrl.apps import config
from finrl.neo_finrl.preprocessor.preprocessors import FeatureEngineer, data_split,roll_data

from finrl.neo_finrl.env_stock_trading.env_stocktrading import StockTradingEnv
# RL models from stable-baselines

from stable_baselines3 import A2C
from stable_baselines3 import PPO
from stable_baselines3 import TD3
from stable_baselines3.td3.policies import MlpPolicy
from stable_baselines3.common.noise import (
    NormalActionNoise,
    OrnsteinUhlenbeckActionNoise,
)
from stable_baselines3.ppo import MlpPolicy
from stable_baselines3.common.vec_env import DummyVecEnv

from stable_baselines3 import DDPG
from stable_baselines3.common.noise import (
    NormalActionNoise,
    OrnsteinUhlenbeckActionNoise,
)
from stable_baselines3 import SAC


MODELS = {"a2c": A2C, "ddpg": DDPG, "td3": TD3, "sac": SAC, "ppo": PPO}

MODEL_KWARGS = {x: config.__dict__[f"{x.upper()}_PARAMS"] for x in MODELS.keys()}

NOISE = {
    "normal": NormalActionNoise,
    "ornstein_uhlenbeck": OrnsteinUhlenbeckActionNoise,
}


class DRLAgent:
    """Provides implementations for DRL algorithms

    Attributes
    ----------
        env: gym environment class
            user-defined class

    Methods
    -------
        train_PPO()
            the implementation for PPO algorithm
        train_A2C()
            the implementation for A2C algorithm
        train_DDPG()
            the implementation for DDPG algorithm
        train_TD3()
            the implementation for TD3 algorithm
        train_SAC()
            the implementation for SAC algorithm
        DRL_prediction()
            make a prediction in a test dataset and get results
    """

    @staticmethod
    def DRL_prediction(model, environment):
        test_env, test_obs = environment.get_sb_env()
        """make a prediction"""
        account_memory = []
        actions_memory = []
        test_env.reset()
        for i in range(len(environment.train_set.index.unique())):
            action, _states = model.predict(test_obs)
            #account_memory = test_env.env_method(method_name="save_asset_memory")
            #actions_memory = test_env.env_method(method_name="save_action_memory")
            test_obs, rewards, dones, info = test_env.step(action)
            if i == (len(environment.train_set.index.unique()) - 2):
              account_memory = test_env.env_method(method_name="save_asset_memory")
              actions_memory = test_env.env_method(method_name="save_action_memory")
            if dones[0]:
                print("hit end!")
                break
        return account_memory[0], actions_memory[0]

    def __init__(self, env):
        self.env = env

    def get_model(
        self,
        model_name,
        policy="MlpPolicy",
        policy_kwargs=None,
        model_kwargs=None,
        verbose=1,
    ):
        if model_name not in MODELS:
            raise NotImplementedError("NotImplementedError")

        if model_kwargs is None:
            model_kwargs = MODEL_KWARGS[model_name]

        if "action_noise" in model_kwargs:
            n_actions = self.env.action_space.shape[-1]
            model_kwargs["action_noise"] = NOISE[model_kwargs["action_noise"]](
                mean=np.zeros(n_actions), sigma=0.1 * np.ones(n_actions)
            )
        print(model_kwargs)
        model = MODELS[model_name](
            policy=policy,
            env=self.env,
            tensorboard_log=f"{config.TENSORBOARD_LOG_DIR}/{model_name}",
            verbose=verbose,
            policy_kwargs=policy_kwargs,
            **model_kwargs,
        )
        return model

    def train_model(self, model, tb_log_name, total_timesteps=5000):
        model = model.learn(total_timesteps=total_timesteps, tb_log_name=tb_log_name)
        return model


class DRLEnsembleAgent:
    @staticmethod
    def get_model(model_name,
                    env,
                    policy="MlpPolicy",
                    policy_kwargs=None,
                    model_kwargs=None,
                    verbose=1):

        if model_name not in MODELS:
            raise NotImplementedError("NotImplementedError")

        if model_kwargs is None:
            temp_model_kwargs = MODEL_KWARGS[model_name]
        else:
            temp_model_kwargs = model_kwargs.copy()

        if "action_noise" in temp_model_kwargs:
            n_actions = env.action_space.shape[-1]
            temp_model_kwargs["action_noise"] = NOISE[temp_model_kwargs["action_noise"]](
                mean=np.zeros(n_actions), sigma=0.1 * np.ones(n_actions)
            )
        print(temp_model_kwargs)
        model = MODELS[model_name](
            policy=policy,
            env=env,
            tensorboard_log=f"{config.TENSORBOARD_LOG_DIR}/{model_name}",
            verbose=verbose,
            policy_kwargs=policy_kwargs,
            **temp_model_kwargs,
        )
        return model

    @staticmethod
    def train_model(model, model_name, tb_log_name, iter_num, total_timesteps=5000):
        model = model.learn(total_timesteps=total_timesteps, tb_log_name=tb_log_name)
        model.save(f"{config.TRAINED_MODEL_DIR}/{model_name.upper()}_{total_timesteps//1000}k_{iter_num}")
        return model

    @staticmethod
    def get_validation_sharpe(iteration,model_name):
        ###Calculate Sharpe ratio based on validation results###
        df_total_value = pd.read_csv('results/account_value_validation_{}_{}.csv'.format(model_name,iteration))
        sharpe = (4 ** 0.5) * df_total_value['pct_return'].mean() / \
                 df_total_value['pct_return'].std()
        return sharpe

    def __init__(self,train_set,test_set,
                validation_window,
                stock_dim,
                hmax,                
                initial_amount,
                buy_cost_pct,
                sell_cost_pct,
                reward_scaling,
                state_space,
                action_space,
                tech_indicator_list,
                print_verbosity):

        self.train_set = train_set
        self.test_set = test_set

        self.unique_trade_date = train_set.date.unique()
        self.validation_window = validation_window

        self.stock_dim = stock_dim
        self.hmax = hmax
        self.initial_amount = initial_amount
        self.buy_cost_pct = buy_cost_pct
        self.sell_cost_pct = sell_cost_pct
        self.reward_scaling = reward_scaling
        self.state_space = state_space
        self.action_space = action_space
        self.tech_indicator_list = tech_indicator_list
        self.print_verbosity = print_verbosity


    def DRL_validation(self, model, test_data, test_env, test_obs):
        ###validation process###
        for i in range(len(test_data.index.unique())):
            action, _states = model.predict(test_obs)
            test_obs, rewards, dones, info = test_env.step(action)

    def DRL_prediction(self,model,name,last_state,turbulence_threshold,initial,iter_num):
        ### make a prediction based on trained model###

        ## trading env
        # trade_data = data_split(self.train_set, start=self.unique_trade_date[iter_num - self.validation_window], end=self.unique_trade_date[iter_num])
        # trade_data = self.train_set[iter_num - self.validation_window:iter_num]
        trade_data = roll_data(df=self.test_set,iter_start=iter_num,window_size=self.validation_window)
        try:
            trade_env = DummyVecEnv([lambda: StockTradingEnv(trade_data,
                                                            self.stock_dim,
                                                            self.hmax,
                                                            self.initial_amount,
                                                            self.buy_cost_pct,
                                                            self.sell_cost_pct,
                                                            self.reward_scaling,
                                                            self.state_space,
                                                            self.action_space,
                                                            self.tech_indicator_list,
                                                            turbulence_threshold=turbulence_threshold,
                                                            initial=initial,
                                                            previous_state=last_state,
                                                            model_name=name,
                                                            mode='trade',
                                                            iteration=iter_num,
                                                            print_verbosity=self.print_verbosity)])
        except:
            return

        trade_obs = trade_env.reset()

        for i in range(len(trade_data.index.unique())):
            action, _states = model.predict(trade_obs)
            trade_obs, rewards, dones, info = trade_env.step(action)
            if i == (len(trade_data.index.unique()) - 2):
                # print(env_test.render())
                last_state = trade_env.render()

        df_last_state = pd.DataFrame({'last_state': last_state})
        df_last_state.to_csv('results/last_state_{}_{}.csv'.format(name, i), index=False)
        return last_state

    def run_ensemble_strategy(self,A2C_model_kwargs,PPO_model_kwargs,DDPG_model_kwargs,timesteps_dict):
        """Ensemble Strategy that combines PPO, A2C and DDPG"""
        print("============Start Ensemble Strategy============")
        # for ensemble model, it's necessary to feed the last state
        # of the previous model to the current model as the initial state
        last_state_ensemble = []

        ppo_sharpe_list = []
        ddpg_sharpe_list = []
        a2c_sharpe_list = []

        model_use = []
        validation_start_date_list = []
        validation_end_date_list = []
        iteration_list = []

        insample_turbulence = self.train_set
        insample_turbulence_threshold = np.quantile(insample_turbulence.turbulence.values, .90)

        start = time.time()
        for i in range(self.validation_window, len(self.unique_trade_date),self.validation_window):
            validation_start_date = self.unique_trade_date[i - self.validation_window]
            validation_end_date = self.unique_trade_date[i - self.validation_window]

            validation_start_date_list.append(validation_start_date)
            validation_end_date_list.append(validation_end_date)
            iteration_list.append(i)

            print("============================================")
            ## initial state is empty
            if i - self.validation_window == 0:
                # inital state
                initial = True
            else:
                # previous state
                initial = False

            # Tuning trubulence index based on historical data
            # Turbulence lookback window is one quarter (63 days)
            end_date_index = self.train_set.index[self.train_set["date"] == self.unique_trade_date[i - self.validation_window]].to_list()[-1]
            start_date_index = end_date_index - 63 + 1

            historical_turbulence = self.train_set.iloc[start_date_index:(end_date_index + 1), :]

            historical_turbulence = historical_turbulence.drop_duplicates(subset=['date'])

            historical_turbulence_mean = np.mean(historical_turbulence.turbulence.values)

            #print(historical_turbulence_mean)

            if historical_turbulence_mean > insample_turbulence_threshold:
                # if the mean of the historical data is greater than the 90% quantile of insample turbulence data
                # then we assume that the current market is volatile,
                # therefore we set the 90% quantile of insample turbulence data as the turbulence threshold
                # meaning the current turbulence can't exceed the 90% quantile of insample turbulence data
                turbulence_threshold = insample_turbulence_threshold
            else:
                # if the mean of the historical data is less than the 90% quantile of insample turbulence data
                # then we tune up the turbulence_threshold, meaning we lower the risk
                turbulence_threshold = np.quantile(insample_turbulence.turbulence.values, 1)
                
            turbulence_threshold = np.quantile(insample_turbulence.turbulence.values, 0.99) 
            print("turbulence_threshold: ", turbulence_threshold)

            ############## Environment Setup starts ##############
            ## training env
            # train = data_split(self.train_set, start=self.train_set.date[0], end=self.train_set.date[i - self.validation_window])
            # train = self.train_set[i - self.validation_window:i]
            train = roll_data(df=self.train_set, iter_start=i, window_size=self.validation_window)
            if isinstance(train,bool):
                continue
            self.train_env = DummyVecEnv([lambda: StockTradingEnv(train,
                                                                self.stock_dim,
                                                                self.hmax,
                                                                self.initial_amount,
                                                                self.buy_cost_pct,
                                                                self.sell_cost_pct,
                                                                self.reward_scaling,
                                                                self.state_space,
                                                                self.action_space,
                                                                self.tech_indicator_list,
                                                                print_verbosity=self.print_verbosity)])

            # validation = data_split(self.test_set, start=self.test_set.date[0],end=self.unique_trade_date[i - self.validation_window])
            # validation = self.test_set[i - self.validation_window:i]
            validation = roll_data(df=self.train_set, iter_start=i, window_size=self.validation_window,val=True)
            if isinstance(validation,bool):
                continue
            ############## Environment Setup ends ##############

            ############## Training and Validation starts ##############
            print("======Model training from: ",self.train_set.date[0], "to ",self.train_set.date[i - self.validation_window])
            # print("training: ",len(data_split(train_set, start=20090000, end=test.datadate.unique()[i-rebalance_window]) ))
            # print("==============Model Training===========")
            print("======A2C Training========")
            model_a2c = self.get_model("a2c",self.train_env,policy="MlpPolicy",model_kwargs=A2C_model_kwargs)
            model_a2c = self.train_model(model_a2c, "a2c", tb_log_name="a2c_{}".format(i), iter_num = i, total_timesteps=timesteps_dict['a2c']) #100_000

            print("======A2C Validation from: ", validation_start_date, "to ",validation_end_date)
            val_env_a2c = DummyVecEnv([lambda: StockTradingEnv(validation,
                                                                self.stock_dim,
                                                                self.hmax,
                                                                self.initial_amount,
                                                                self.buy_cost_pct,
                                                                self.sell_cost_pct,
                                                                self.reward_scaling,
                                                                self.state_space,
                                                                self.action_space,
                                                                self.tech_indicator_list,
                                                                turbulence_threshold=turbulence_threshold,
                                                                iteration=i,
                                                                model_name='A2C',
                                                                mode='validation',
                                                                print_verbosity=self.print_verbosity)])
            val_obs_a2c = val_env_a2c.reset()
            self.DRL_validation(model=model_a2c,test_data=validation,test_env=val_env_a2c,test_obs=val_obs_a2c)
            sharpe_a2c = self.get_validation_sharpe(i,model_name="A2C")
            print("A2C Sharpe Ratio: ", sharpe_a2c)

            print("======PPO Training========")
            model_ppo = self.get_model("ppo",self.train_env,policy="MlpPolicy",model_kwargs=PPO_model_kwargs)
            model_ppo = self.train_model(model_ppo, "ppo", tb_log_name="ppo_{}".format(i), iter_num = i, total_timesteps=timesteps_dict['ppo']) #100_000
            print("======PPO Validation from: ", validation_start_date, "to ",validation_end_date)
            val_env_ppo = DummyVecEnv([lambda: StockTradingEnv(validation,
                                                                self.stock_dim,
                                                                self.hmax,
                                                                self.initial_amount,
                                                                self.buy_cost_pct,
                                                                self.sell_cost_pct,
                                                                self.reward_scaling,
                                                                self.state_space,
                                                                self.action_space,
                                                                self.tech_indicator_list,
                                                                turbulence_threshold=turbulence_threshold,
                                                                iteration=i,
                                                                model_name='PPO',
                                                                mode='validation',
                                                                print_verbosity=self.print_verbosity)])
            val_obs_ppo = val_env_ppo.reset()
            self.DRL_validation(model=model_ppo,test_data=validation,test_env=val_env_ppo,test_obs=val_obs_ppo)
            sharpe_ppo = self.get_validation_sharpe(i,model_name="PPO")
            print("PPO Sharpe Ratio: ", sharpe_ppo)

            print("======DDPG Training========")
            model_ddpg = self.get_model("ddpg",self.train_env,policy="MlpPolicy",model_kwargs=DDPG_model_kwargs)
            model_ddpg = self.train_model(model_ddpg, "ddpg", tb_log_name="ddpg_{}".format(i), iter_num = i, total_timesteps=timesteps_dict['ddpg'])  #50_000
            print("======DDPG Validation from: ", validation_start_date, "to ",validation_end_date)
            val_env_ddpg = DummyVecEnv([lambda: StockTradingEnv(validation,
                                                                self.stock_dim,
                                                                self.hmax,
                                                                self.initial_amount,
                                                                self.buy_cost_pct,
                                                                self.sell_cost_pct,
                                                                self.reward_scaling,
                                                                self.state_space,
                                                                self.action_space,
                                                                self.tech_indicator_list,
                                                                turbulence_threshold=turbulence_threshold,
                                                                iteration=i,
                                                                model_name='DDPG',
                                                                mode='validation',
                                                                print_verbosity=self.print_verbosity)])
            val_obs_ddpg = val_env_ddpg.reset()
            self.DRL_validation(model=model_ddpg,test_data=validation,test_env=val_env_ddpg,test_obs=val_obs_ddpg)
            sharpe_ddpg = self.get_validation_sharpe(i,model_name="DDPG")

            ppo_sharpe_list.append(sharpe_ppo)
            a2c_sharpe_list.append(sharpe_a2c)
            ddpg_sharpe_list.append(sharpe_ddpg)

            print("======Best Model Retraining from: ", self.train_set.date[0], "to ",self.train_set.date[i - self.validation_window])
            # Environment setup for model retraining up to first trade date
            #train_full = data_split(self.train_set, start=self.train_period[0], end=self.unique_trade_date[i - self.rebalance_window])
            #self.train_full_env = DummyVecEnv([lambda: StockTradingEnv(train_full,
            #                                                    self.stock_dim,
            #                                                    self.hmax,
            #                                                    self.initial_amount,
            #                                                    self.buy_cost_pct,
            #                                                    self.sell_cost_pct,
            #                                                    self.reward_scaling,
            #                                                    self.state_space,
            #                                                    self.action_space,
            #                                                    self.tech_indicator_list,
            #                                                    print_verbosity=self.print_verbosity)])
            # Model Selection based on sharpe ratio
            if (sharpe_ppo >= sharpe_a2c) & (sharpe_ppo >= sharpe_ddpg):
                model_use.append('PPO')
                model_ensemble = model_ppo

                #model_ensemble = self.get_model("ppo",self.train_full_env,policy="MlpPolicy",model_kwargs=PPO_model_kwargs)
                #model_ensemble = self.train_model(model_ensemble, "ensemble", tb_log_name="ensemble_{}".format(i), iter_num = i, total_timesteps=timesteps_dict['ppo']) #100_000
            elif (sharpe_a2c > sharpe_ppo) & (sharpe_a2c > sharpe_ddpg):
                model_use.append('A2C')
                model_ensemble = model_a2c

                #model_ensemble = self.get_model("a2c",self.train_full_env,policy="MlpPolicy",model_kwargs=A2C_model_kwargs)
                #model_ensemble = self.train_model(model_ensemble, "ensemble", tb_log_name="ensemble_{}".format(i), iter_num = i, total_timesteps=timesteps_dict['a2c']) #100_000
            else:
                model_use.append('DDPG')
                model_ensemble = model_ddpg

                #model_ensemble = self.get_model("ddpg",self.train_full_env,policy="MlpPolicy",model_kwargs=DDPG_model_kwargs)
                #model_ensemble = self.train_model(model_ensemble, "ensemble", tb_log_name="ensemble_{}".format(i), iter_num = i, total_timesteps=timesteps_dict['ddpg']) #50_000

            ############## Training and Validation ends ##############

            ############## Trading starts ##############
            print("======Trading from: ", self.test_set.date[0], "to ", self.unique_trade_date[i])
            #print("Used Model: ", model_ensemble)
            last_state_ensemble = self.DRL_prediction(model=model_ensemble, name="ensemble",
                                                     last_state=last_state_ensemble,
                                                     turbulence_threshold = turbulence_threshold,
                                                     initial=initial,iter_num=i)
            ############## Trading ends ##############

        end = time.time()
        print("Ensemble Strategy took: ", (end - start) / 60, " minutes")

        df_summary = pd.DataFrame([iteration_list,validation_start_date_list,validation_end_date_list,model_use,a2c_sharpe_list,ppo_sharpe_list,ddpg_sharpe_list]).T
        df_summary.columns = ['Iter','Val Start','Val End','Model Used','A2C Sharpe','PPO Sharpe','DDPG Sharpe']

        return df_summary





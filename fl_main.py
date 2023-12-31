import numpy as np 
import pandas as pd

import algo
import federated
import scripts

import os
import json
import random

rand_seed = 42
np.random.seed(rand_seed)
random.seed(rand_seed)

dataset = 'purchase'
x_target_train, y_target_train, x_target_test, y_target_test = scripts.load_purchase(rand_seed)
# x_target_train, y_target_train, x_target_test, y_target_test = scripts.load_loan(rand_seed, tr_size=10000)
#x_target_train, y_target_train, x_target_test, y_target_test = scripts.load_texas()

number_of_clients = 32
fl_iterations = 10
data_per_client = int(x_target_train.shape[0]/number_of_clients)

#create clients with set training parameters and datasets
clients = {}
for i in range(number_of_clients):
    clients[i] = algo.LogisticRegression_DPSGD()

    clients[i].n_classes      = len(np.unique(y_target_test))
    clients[i].alpha          = 0.001
    clients[i].max_iter       = 100
    clients[i].lambda_        = 1e-4
    clients[i].tolerance      = 1e-6
    clients[i].sgdDP          = False
    clients[i].L              = 1 
    clients[i].epsilon        = 1
    clients[i].C              = 1
    clients[i].outDP_local          = True
    clients[i].outDP_local_epsilon  = 10000

    params = dict(clients[0].__dict__)

    clients[i].x = x_target_train[i*data_per_client:(i+1)*data_per_client]
    clients[i].y = y_target_train[i*data_per_client:(i+1)*data_per_client]

fl_path = f'{dataset}fl/rs{rand_seed}_ncl{number_of_clients}_fiter{fl_iterations}_lr{clients[0].alpha}_iter{clients[0].max_iter}_reg{clients[0].lambda_}'
if clients[0].sgdDP:
    fl_path += f'_sgdDP{clients[0].sgdDP}_eps{clients[0].epsilon}_L{clients[0].L}_C{clients[0].C}'
if clients[i].outDP_local:
    fl_path += f'_outDPlocal{clients[0].outDP_local}_eps{clients[0].outDP_local_epsilon}'

params.pop('x')
params.pop('y')
print(params)
if os.path.exists(fl_path): 
    print('Experiment already exists:\n', fl_path)
else:
    print('Creating new experiment:\n', fl_path)
    os.mkdir(fl_path)
    with open(fl_path+'/params.json', 'w') as file:
        json.dump(params, file)
    results = {}
    for iteration in range(fl_iterations):

        print(iteration, ' FL iteration')
        for i in clients:
            print("Start training client: ", i)
            federated.train_client(iteration, clients[i], x_target_test, y_target_test)
            if clients[i].outDP_local:
                print('Adding local output DP')
                federated.output_DP_federated(clients[i],  clients[i].x.shape[0], clients[i].outDP_local_epsilon)
                clients[i].train_acc_outDP_local = clients[i].evaluate(clients[i].x, clients[i].y, acc=True)
                clients[i].test_acc_outDP_local = clients[i].evaluate(x_target_test, y_target_test, acc=True)
                np.save(fl_path + f'/i{iteration}_c{i}_before_DP', clients[i].theta_before_noise)
                np.save(fl_path + f'/i{iteration}_c{i}', clients[i].theta)
                results[f'i{iteration}_c{i}'] = (clients[i].train_acc,  clients[i].test_acc, clients[i].train_acc_outDP_local, clients[i].test_acc_outDP_local)
            else:
                np.save(fl_path + f'/i{iteration}_c{i}', clients[i].theta)
                results[f'i{iteration}_c{i}'] = (clients[i].train_acc,  clients[i].test_acc)
                
        global_model = federated.aggregate(clients)
        np.save(fl_path + f'/i{iteration}_g', global_model)
        federated.update_clients(clients, global_model)
        
        #global model evaluation
        print('Global model evaluataion:')
        gtrain_acc = clients[0].evaluate(x_target_train, y_target_train, acc=True)
        gtest_acc = clients[0].evaluate(x_target_test, y_target_test, acc=True)
        results[f'i{iteration}_g'] = (gtrain_acc,  gtest_acc)
        if False and clients[0].evaluate(x_target_test, y_target_test)>=0.56:
                break
    
    if clients[i].outDP_local:
        res = pd.DataFrame.from_dict(results, orient='index', columns=['train_acc', 'test_acc', 'train_acc_outDP', 'test_acc_out_DP'])
    else:    
        res = pd.DataFrame.from_dict(results, orient='index', columns=['train_acc', 'test_acc'])                
    res.to_csv(fl_path + f'/results.csv')

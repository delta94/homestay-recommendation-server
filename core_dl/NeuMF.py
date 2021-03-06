import numpy as np
import keras
from keras import backend as K
from keras import initializers
from keras.regularizers import l1, l2
from keras.models import Sequential, Model
from keras.layers.core import Dense, Lambda, Activation
from keras.layers import Embedding, Input, Dense, Reshape, Flatten, Dropout,Concatenate,Multiply,concatenate,multiply
from keras.optimizers import Adagrad, Adam, SGD, RMSprop
from evaluate import evaluate_model
from DatasetLuxstay import DatasetLuxstay
from time import time
import sys
import argparse
import pandas as pd

dfUser = pd.read_csv('user_mapping.csv', sep="\s+")
dfRoom = pd.read_csv('room_mapping.csv', sep="\s+")
user_mapping_arr = np.array(dfUser)
room_mapping_arr = np.array(dfRoom)

import math

def sigmoid(x):
  return 2 / (1 + math.exp(-x)) - 1


#################### Arguments ####################


def parse_args():
    parser = argparse.ArgumentParser(description="Run NeuMF.")
    parser.add_argument('--path', nargs='?', default='Data/',
                        help='Input data path.')
    parser.add_argument('--dataset', nargs='?', default='ml-1m',
                        help='Choose a dataset.')
    parser.add_argument('--epochs', type=int, default=100,
                        help='Number of epochs.')
    parser.add_argument('--batch_size', type=int, default=256,
                        help='Batch size.')
    parser.add_argument('--num_factors', type=int, default=8,
                        help='Embedding size of MF model.')
    parser.add_argument('--layers', nargs='?', default='[64,32,16,8]',
                        help="MLP layers. Note that the first layer is the concatenation of user and item embeddings. So layers[0]/2 is the embedding size.")
    parser.add_argument('--reg_mf', type=float, default=0,
                        help='Regularization for MF embeddings.')
    parser.add_argument('--reg_layers', nargs='?', default='[0,0,0,0]',
                        help="Regularization for each MLP layer. reg_layers[0] is the regularization for embeddings.")
    parser.add_argument('--num_neg', type=int, default=4,
                        help='Number of negative instances to pair with a positive instance.')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate.')
    parser.add_argument('--learner', nargs='?', default='adam',
                        help='Specify an optimizer: adagrad, adam, rmsprop, sgd')
    parser.add_argument('--verbose', type=int, default=1,
                        help='Show performance per X iterations')
    parser.add_argument('--out', type=int, default=1,
                        help='Whether to save the trained model.')
    parser.add_argument('--mf_pretrain', nargs='?', default='',
                        help='Specify the pretrain model file for MF part. If empty, no pretrain will be used')
    parser.add_argument('--mlp_pretrain', nargs='?', default='',
                        help='Specify the pretrain model file for MLP part. If empty, no pretrain will be used')
    return parser.parse_args()


def init_normal(shape, name=None):
    return initializations.normal(shape, scale=0.01, name=name)



def get_model(num_users, num_items, mf_dim=10, layers=[10], reg_layers=[0], reg_mf=0):
    assert len(layers) == len(reg_layers)
    num_layer = len(layers)  # Number of layers in the MLP
    # Input variables
    user_input = Input(shape=(1,), dtype='int32', name='user_input')
    item_input = Input(shape=(1,), dtype='int32', name='item_input')

    # Embedding layer
    MF_Embedding_User = Embedding(input_dim=num_users, output_dim=mf_dim, name='mf_embedding_user',
                                  embeddings_initializer=initializers.VarianceScaling(scale=0.01, mode='fan_in', distribution='normal', seed=None), embeddings_regularizer=l2(reg_mf), input_length=1)
    MF_Embedding_Item = Embedding(input_dim=num_items, output_dim=mf_dim, name='mf_embedding_item',
                                embeddings_initializer=initializers.VarianceScaling(scale=0.01, mode='fan_in', distribution='normal', seed=None),embeddings_regularizer=l2(reg_mf), input_length=1)

    MLP_Embedding_User = Embedding(input_dim=num_users, output_dim=int(layers[0]/2), name="mlp_embedding_user",
                                embeddings_initializer=initializers.VarianceScaling(scale=0.01, mode='fan_in', distribution='normal', seed=None),embeddings_regularizer=l2(reg_layers[0]), input_length=1)
    MLP_Embedding_Item = Embedding(input_dim=num_items, output_dim=int(layers[0]/2), name='mlp_embedding_item',
                                embeddings_initializer=initializers.VarianceScaling(scale=0.01, mode='fan_in', distribution='normal', seed=None),embeddings_regularizer=l2(reg_layers[0]), input_length=1)
    # MF part
    mf_user_latent = Flatten()(MF_Embedding_User(user_input))
    mf_item_latent = Flatten()(MF_Embedding_Item(item_input))
    mf_vector = multiply([mf_user_latent, mf_item_latent])
    # MLP part
    mlp_user_latent = Flatten()(MLP_Embedding_User(user_input))
    mlp_item_latent = Flatten()(MLP_Embedding_Item(item_input))
    mlp_vector = concatenate([mlp_user_latent, mlp_item_latent],axis=1)
    for idx in range(1, num_layer):
        layer = Dense(output_dim=int(layers[idx]), kernel_regularizer=l2(
            reg_layers[idx]), activation='relu', name="layer%d" % idx)
        # layer.trainable = False
        mlp_vector = layer(mlp_vector)
    predict_vector = concatenate([mf_vector, mlp_vector],axis=1)
    # Final prediction layer
    prediction_layer = Dense(1, activation='sigmoid',
                             kernel_initializer='lecun_uniform', name="prediction")
    prediction_layer.trainable = True
    prediction = prediction_layer(predict_vector)
    print('end')
    return Model(input=[user_input, item_input], output=prediction)





def get_train_instances(train, num_negatives,test_negatives):
    user_input, item_input, labels = [], [], []
    num_users = train.shape[0]
    for (u, i) in train.keys():
        # positive instance
        user_input.append(u)
        item_input.append(i)
        value = int(train[u,i])
        labels.append(sigmoid(value))
        # negative instances
        for t in range(num_negatives):
            j = np.random.randint(num_items)
            test_negatives = np.array(test_negatives)
            current_user = test_negatives[u,:]
            while (((u, j) in train) or (j in current_user)):
                j = np.random.randint(num_items)
            user_input.append(u)
            item_input.append(j)
            labels.append(0)
    return user_input, item_input, labels


if __name__ == '__main__':
    args = parse_args()
    num_epochs = args.epochs
    batch_size = args.batch_size
    mf_dim = args.num_factors
    layers = eval(args.layers)
    reg_mf = args.reg_mf
    reg_layers = eval(args.reg_layers)
    num_negatives = args.num_neg
    learning_rate = args.lr
    learner = args.learner
    verbose = args.verbose
    mf_pretrain = args.mf_pretrain
    mlp_pretrain = args.mlp_pretrain
    print('Check learning rate: ',learning_rate)
    topK = 10
    evaluation_threads = 1  # mp.cpu_count()
    print("NeuMF arguments: %s " % (args))
    model_out_file = 'Pretrain/%s_NeuMF_%d_%s_%d.h5' % (
        args.dataset, mf_dim, args.layers, time())

    # Loading data
    t1 = time()
    dataset = DatasetLuxstay()
    train, testRatings, testNegatives = dataset.trainMatrix, dataset.testRatings, dataset.testNegatives
    num_users, num_items = train.shape
    print("Load data done [%.1f s]. #user=%d, #item=%d, #train=%d, #test=%d"
          % (time()-t1, num_users, num_items, train.nnz, len(testRatings)))

    # Build model
    model = get_model(num_users+10000, num_items+10000,
                      mf_dim, layers, reg_layers, reg_mf)
    model.compile(optimizer=Adam(lr=learning_rate),loss='binary_crossentropy',metrics=["accuracy"])

    # Init performance
    (hits, ndcgs) = evaluate_model(model, testRatings,
                                   testNegatives, topK, evaluation_threads)
    hr, ndcg = np.array(hits).mean(), np.array(ndcgs).mean()
    print('Init: HR = %.4f, NDCG = %.4f' % (hr, ndcg))
    best_hr, best_ndcg, best_iter = hr, ndcg, -1
    if args.out > 0:
        model.save_weights(model_out_file, overwrite=True)

    # Training model
    for epoch in range(num_epochs):
        t1 = time()
        # Generate training instances
        user_input, item_input, labels = get_train_instances(
            train, num_negatives,testNegatives)

        # Training
        hist = model.fit([np.array(user_input), np.array(item_input)],  # input
                         np.array(labels),  # labels
                         batch_size=batch_size, nb_epoch=1, verbose=0, shuffle=True)
        t2 = time()

        # Evaluation
        if epoch % verbose == 0:
            (hits, ndcgs) = evaluate_model(model, testRatings,
                                           testNegatives, topK, evaluation_threads)
            hr, ndcg, loss,acc = np.array(hits).mean(), np.array(
                ndcgs).mean(), hist.history['loss'][0],hist.history['acc'][0]
            print('Iteration %d [%.1f s]: HR = %.4f, NDCG = %.4f, loss = %.4f [%.1f s], acc=%.4f'
                  % (epoch,  t2-t1, hr, ndcg, loss, time()-t2,acc))
            if hr > best_hr:
                best_hr, best_ndcg, best_iter = hr, ndcg, epoch
                if args.out > 0:
                    model.save_weights(model_out_file, overwrite=True)

    print("End. Best Iteration %d:  HR = %.4f, NDCG = %.4f. " %
          (best_iter, best_hr, best_ndcg))
    if args.out > 0:
        print("The best NeuMF model is saved to %s" % (model_out_file))

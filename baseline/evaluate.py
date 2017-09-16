from __future__ import division, print_function, absolute_import

import os

import numpy as np


os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"  # see issue #152
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
import tensorflow as tf

from keras.preprocessing import image
from keras.applications.resnet50 import preprocess_input
from keras.models import Model
from keras.backend.tensorflow_backend import set_session
from keras.models import load_model
from util import write

project_path = '/home/cwh/coding/rank-reid'

'''
DATASET = project_path + '../dataset/Duke'
TEST = os.path.join(DATASET, 'bounding_box_test')
TEST_NUM = 17661
QUERY = os.path.join(DATASET, 'query')
QUERY_NUM = 2228
'''

DATASET = project_path + '/dataset/Market'
TEST = os.path.join(DATASET, 'test')
TEST_NUM = 19732
TRAIN = os.path.join(DATASET, 'train')
TRAIN_NUM = 12936
QUERY = os.path.join(DATASET, 'probe')
QUERY_NUM = 3368

'''
DATASET = project_path + '/dataset/CUHK03'
TEST = os.path.join(DATASET, 'bbox_test')
TEST_NUM = 5332
QUERY = os.path.join(DATASET, 'query')
QUERY_NUM = 1400
'''


def extract_info(dir_path):
    infos = []
    for image_name in sorted(os.listdir(dir_path)):
        arr = image_name.split('_')
        person = int(arr[0])
        camera = int(arr[1][1])
        infos.append((person, camera))

    return infos


def extract_feature(dir_path, net):
    features = []
    infos = []
    num = 0
    for image_name in sorted(os.listdir(dir_path)):
        if 'jpg' not in image_name \
            and 'bmp' not in image_name \
            and 'jpeg' not in image_name \
            and 'bmp' not in image_name \
            and 'png' not in image_name:
            continue
        if 's' not in image_name:
            # grid
            arr = image_name.split('_')
            person = int(arr[0])
            camera = -1
        elif 's' in image_name:
            #market
            arr = image_name.split('_')
            person = int(arr[0])
            camera = int(arr[1][1])
        else:
            continue
        image_path = os.path.join(dir_path, image_name)
        img = image.load_img(image_path, target_size=(224, 224))
        x = image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)
        feature = net.predict(x)
        features.append(np.squeeze(feature))
        infos.append((person, camera))

    return features, infos


def similarity_matrix(query_f, test_f):
    # Tensorflow graph
    # use GPU to calculate the similarity matrix
    query_t = tf.placeholder(tf.float32, (None, None))
    test_t = tf.placeholder(tf.float32, (None, None))
    query_t_norm = tf.nn.l2_normalize(query_t, dim=1)
    test_t_norm = tf.nn.l2_normalize(test_t, dim=1)
    tensor = tf.matmul(query_t_norm, test_t_norm, transpose_a=False, transpose_b=True)

    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    sess = tf.Session(config=config)
    set_session(sess)

    result = sess.run(tensor, {query_t: query_f, test_t: test_f})
    print(result.shape)
    # descend
    return result


def sort_similarity(query_f, test_f):
    result = similarity_matrix(query_f, test_f)
    result_argsort = np.argsort(-result, axis=1)
    print(result_argsort.shape)
    np.savetxt('resnet50_predict_market.txt', result_argsort, fmt='%d')
    return result, result_argsort


def map_rank_eval(query_info, test_info, result_argsort):
    # about 10% lower than matlab result
    # for evaluate rank1 and map
    match = []
    junk = []

    for q_index, (qp, qc) in enumerate(query_info):
        tmp_match = []
        tmp_junk = []
        for t_index, (tp, tc) in enumerate(test_info):
            if tp == qp and qc != tc:
                tmp_match.append(t_index)
            elif tp == qp or tp == -1:
                tmp_junk.append(t_index)
        match.append(tmp_match)
        junk.append(tmp_junk)

    rank_1 = 0.0
    mAP = 0.0
    test_num = min(TEST_NUM, len(result_argsort[0]))
    for idx in range(len(query_info)):
        if idx % 100 == 0:
            print('evaluate img %d' % idx)
        recall = 0.0
        precision = 1.0
        hit = 0.0
        cnt = 0.0
        ap = 0.0
        YES = match[idx]
        IGNORE = junk[idx]
        rank_flag = True
        for i in range(0, test_num):
            k = result_argsort[idx][i]
            if k in IGNORE:
                continue
            else:
                cnt += 1
                if k in YES:
                    hit += 1
                    if rank_flag:
                        rank_1 += 1
                tmp_recall = hit / len(YES)
                tmp_precision = hit / cnt
                ap = ap + (tmp_recall - recall) * ((precision + tmp_precision) / 2)
                recall = tmp_recall
                precision = tmp_precision
                rank_flag = False
            if hit == len(YES):
                break
        mAP += ap
    rank1_acc = rank_1 / QUERY_NUM
    mAP = mAP / QUERY_NUM
    print('Rank 1:\t%f' % rank1_acc)
    print('mAP:\t%f' % mAP)
    return rank1_acc, mAP


def train_predict(net, train_path, pid_path, score_path):
    net = Model(inputs=[net.input], outputs=[net.get_layer('avg_pool').output])
    train_f, test_info = extract_feature(train_path, net)
    result, result_argsort = sort_similarity(train_f, train_f)
    for i in range(len(result)):
        result[i] = result[i][result_argsort[i]]
    result = np.array(result)
    # ignore top1 because it's the origin image
    np.savetxt(score_path, result[:, 1:], fmt='%.4f')
    np.savetxt(pid_path, result_argsort[:, 1:], fmt='%d')
    return result


def test_predict(net, probe_path, gallery_path, pid_path, score_path):
    net = Model(inputs=[net.input], outputs=[net.get_layer('avg_pool').output])
    test_f, test_info = extract_feature(gallery_path, net)
    query_f, query_info = extract_feature(probe_path, net)
    result, result_argsort = sort_similarity(query_f, test_f)
    for i in range(len(result)):
        result[i] = result[i][result_argsort[i]]
    result = np.array(result)
    # ignore top1 because it's the origin image
    np.savetxt(pid_path, result_argsort, fmt='%d')
    np.savetxt(score_path, result, fmt='%.4f')
    return test_info, query_info
    # map_rank_eval(query_info, test_info, result_argsort)


def market_result_eval(predict_path, log_path='market_eval.log'):
    res = np.genfromtxt(predict_path, delimiter=' ')
    print('predict info get, extract gallery info start')
    test_info = extract_info(TEST)
    print('extract probe info start')
    query_info = extract_info(QUERY)
    print('start evaluate map and rank acc')
    rank1, mAP = map_rank_eval(query_info, test_info, res)
    write(log_path, predict_path + '\n')
    write(log_path, '%f\t%f\n' % (rank1, mAP))


def grid_result_eval(predict_path, log_path='grid_eval.log'):
    pids4probes = np.genfromtxt(predict_path, delimiter=' ')
    probe_shoot = [0, 0, 0, 0, 0]
    for i, pids in enumerate(pids4probes):
        for j, pid in enumerate(pids):
            if pid - i == 775:
                if j == 0:
                    for k in range(5):
                        probe_shoot[k] += 1
                elif j < 5:
                    for k in range(1,5):
                        probe_shoot[k] += 1
                elif j < 10:
                    for k in range(2,5):
                        probe_shoot[k] += 1
                elif j < 20:
                    for k in range(3,5):
                        probe_shoot[k] += 1
                elif j < 50:
                    for k in range(4,5):
                        probe_shoot[k] += 1
                break
    probe_acc = [shoot/len(pids4probes) for shoot in probe_shoot]
    write(log_path, predict_path + '\n')
    write(log_path, '%.2f\t%.2f\t%.2f\n' % (probe_acc[0], probe_acc[1], probe_acc[2]))
    print(predict_path)
    print(probe_acc)


def cuhk_result_eval(predict_path, test_info, probe_info, log_path='grid_eval.log'):
    pids4probes = np.genfromtxt(predict_path, delimiter=' ')
    probe_shoot = [0, 0, 0, 0, 0]
    for i, pids in enumerate(pids4probes):
        for j, pid in enumerate(pids):
            if probe_info[i][0] == test_info[int(pid)][0]:
                if j == 0:
                    for k in range(5):
                        probe_shoot[k] += 1
                elif j < 5:
                    for k in range(1,5):
                        probe_shoot[k] += 1
                elif j < 10:
                    for k in range(2,5):
                        probe_shoot[k] += 1
                elif j < 20:
                    for k in range(3,5):
                        probe_shoot[k] += 1
                elif j < 50:
                    for k in range(4,5):
                        probe_shoot[k] += 1
                break
    probe_acc = [shoot/len(pids4probes) for shoot in probe_shoot]
    write(log_path, predict_path + '\n')
    write(log_path, '%.2f\t%.2f\t%.2f\n' % (probe_acc[0], probe_acc[1], probe_acc[2]))
    print(predict_path)
    print(probe_acc)


if __name__ == '__main__':
    # file_result_eval('../pretrain/test_renew_pid.log')
    # predict_eval()
    # grid_result_eval('../pretrain/grid_cross0_transfer/test_renew_pid.log')
    # grid_result_eval('/home/cwh/coding/rank-reid/vtep.log')
    # [0.504, 0.776, 0.84, 0.896, 0.968]
    market_result_eval('/home/cwh/coding/TrackViz/data/market_market-test/cross_filter_pid.log')
    # market_result_eval('../pretrain/market_market_pid_test.txt')


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import math
import copy
import numpy as np
import shutil
import os
import random

from PyQt5.QtCore import QObject
from PyQt5.QtCore import QThread
from PyQt5.QtCore import pyqtSignal

import matplotlib.pyplot as plt
from sklearn.cluster import AgglomerativeClustering
from sklearn.cluster import DBSCAN
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer

from sources.TextPreprocessing import writeStringToFile, makePreprocessing, makeFakePreprocessing, \
    getCompiledFromSentencesText
from sources.utils import makePreprocessingForAllFilesInFolder
from sklearn.feature_extraction.text import TfidfVectorizer


# Сигналы для потока вычисления

class ClasterizationCalculatorSignals(QObject):
    PrintInfo = pyqtSignal(str)
    Finished = pyqtSignal()
    UpdateProgressBar = pyqtSignal(int)


# Класс-поток вычисления
class ClasteringCalculator(QThread):

    def __init__(self, filenames, output_dir, morph, configurations, textEdit):
        super().__init__()
        self.filenames = filenames
        self.output_dir = output_dir + '/clasterization/'
        self.morph = morph
        self.configurations = configurations
        self.textEdit = textEdit
        self.texts = []
        self.categories = dict()
        self.signals = ClasterizationCalculatorSignals()
        self.method = '1'
        self.minimalWordsLen = 3
        self.clusterCount = 2
        self.eps = 0.01
        self.m = 2
        self.minPts = 0.3
        self.spinbox_ward_eps = 1.0
        self.ward_parameter_clusters_count = 1
        self.need_preprocessing = False
        self.first_call = True
        self.texts = []


    def setMethod(self, method_name):
        self.method = method_name

    def setMinimalWordsLen(self, value):
        self.minimalWordsLen = value

    def setEps(self, value):
        self.eps = value

    def setM(self,value):
        self.m = value

    def setMinPts(self,value):
        self.minPts = value

    def setClusterCount(self,value):
        self.clusterCount = value

    def run(self):
        self.signals.UpdateProgressBar.emit(1)

        if self.first_call:
            if self.need_preprocessing:
                self.signals.PrintInfo.emit("Препроцессинг...")
                self.texts = makePreprocessing(self.filenames, self.morph, self.configurations, self.textEdit)
            else:
                self.signals.PrintInfo.emit("Препроцессинг - пропускается")
                self.texts = makeFakePreprocessing(self.filenames)
        else:
            if self.need_preprocessing:
                self.signals.PrintInfo.emit("Препроцессинг - использование предыдущих результатов.")
            else:
                self.signals.PrintInfo.emit("Препроцессинг - пропускается")

        input_texts = list()
        for text in self.texts:
            input_texts.append(getCompiledFromSentencesText(text.register_pass_centences))
        short_filenames = [text.filename[text.filename.rfind('/') + 1:] for text in self.texts]

        if(self.method == '1'):
            self.make_k_means_clustering(short_filenames, input_texts)

        if(self.method == '2'):
            self.make_dbscan_clustering(short_filenames, input_texts)

        if(self.method == '3'):
            self.make_ward_clustering(short_filenames, input_texts)




        if self.first_call and self.need_preprocessing:
            self.first_call = False

        self.signals.PrintInfo.emit('Рассчеты закончены!')
        self.signals.UpdateProgressBar.emit(100)
        self.signals.Finished.emit()

    def calculate_and_write_idf(self, out_filename, input_texts):
        idf_vectorizer = TfidfVectorizer(min_df=1, use_idf=True)
        idf_vectorizer.fit_transform(input_texts)
        idf = idf_vectorizer.idf_
        tf_idf = dict(zip(idf_vectorizer.get_feature_names(), idf))
        tf_idf_out_text = 'IDF:\n'
        for key, value in tf_idf.items():
            tf_idf_out_text += (str(key) + ';' + str(value) + '\n')
        writeStringToFile(tf_idf_out_text, out_filename)
        result_msg = "Таблица IDF записана: " + out_filename
        return result_msg


    def make_k_means_clustering(self, short_filenames, input_texts):

        output_dir = self.output_dir + 'K_MEANS/'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.signals.PrintInfo.emit("Расчет IDF...")
        idf_filename = output_dir + 'idf.csv'
        msg = self.calculate_and_write_idf(idf_filename, input_texts)
        self.signals.PrintInfo.emit(msg)


        vectorizer = CountVectorizer()
        X = vectorizer.fit_transform(input_texts)

        svd = TruncatedSVD(2)
        normalizer = Normalizer(copy=False)
        lsa = make_pipeline(svd, normalizer)
        X = lsa.fit_transform(X)

        km = KMeans(n_clusters=self.clusterCount, init='k-means++', max_iter=100, n_init=10)
        km.fit(X)

        predict_result = km.predict(X)


        self.signals.PrintInfo.emit('\nПрогноз по документам:\n')

        clasters_output = ''
        for claster_index in range(max(predict_result) + 1):
            clasters_output += ('Кластер ' + str(claster_index) + ':\n')
            for predict, document in zip(predict_result, short_filenames):
                if predict == claster_index:
                    clasters_output += ('  ' + str(document) + '\n')
            clasters_output += '\n'
        self.signals.PrintInfo.emit(clasters_output)

        self.signals.PrintInfo.emit('Сохранено в:' + str(output_dir + 'clusters.txt'))
        writeStringToFile(clasters_output, output_dir + 'clusters.txt')

        self.signals.PrintInfo.emit('')
        self.signals.PrintInfo.emit('Центры кластеров:')
        for index, cluster_center in enumerate(km.cluster_centers_):
            self.signals.PrintInfo.emit('  ' + str(index) + ':' + str(cluster_center))

        plt.subplot(111)
        colors = np.array([x for x in 'bgrcmykbgrcmykbgrcmykbgrcmyk'])
        colors = np.hstack([colors] * 20)
        plt.scatter(X[:, 0], X[:, 1], color=colors[predict_result].tolist(), s=50)

        for label, x, y in zip(short_filenames, X[:, 0], X[:, 1]):
            plt.annotate(
                label,
                xy=(x, y), xytext=(-20, 20),
                textcoords='offset points', ha='right', va='bottom',
                # bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        plt.xticks(())
        plt.yticks(())
        plt.grid()


    def make_dbscan_clustering(self, short_filenames, input_texts):

        output_dir = self.output_dir + 'DBSCAN/'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.signals.PrintInfo.emit("Расчет IDF...")
        idf_filename = output_dir + 'idf.csv'
        msg = self.calculate_and_write_idf(idf_filename, input_texts)
        self.signals.PrintInfo.emit(msg)


        vectorizer = CountVectorizer()
        X = vectorizer.fit_transform(input_texts)

        svd = TruncatedSVD(2)
        normalizer = Normalizer(copy=False)
        lsa = make_pipeline(svd, normalizer)
        X = lsa.fit_transform(X)

        db = DBSCAN(eps=self.eps, min_samples=self.minPts)
        predict_result = db.fit_predict(X)
        db.fit(X)

        core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
        core_samples_mask[db.core_sample_indices_] = True
        labels = db.labels_

        # Number of clusters in labels, ignoring noise if present.
        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)

        self.signals.PrintInfo.emit('\nПрогноз по документам:\n')
        clasters_output = ''
        for claster_index in range(max(predict_result) + 1):
            clasters_output += ('Кластер ' + str(claster_index) + ':\n')
            for predict, document in zip(predict_result, short_filenames):
                if predict == claster_index:
                    clasters_output += ('  ' + str(document) + '\n')
            clasters_output += '\n'

        clasters_output += ('Шумовые элементы (-1):\n')
        for predict, document in zip(predict_result, short_filenames):
            if predict == -1:
                clasters_output += ('  ' + str(document) + '\n')
        clasters_output += '\n'
        self.signals.PrintInfo.emit(clasters_output)

        self.signals.PrintInfo.emit('Сохранено в:' + str(output_dir + 'clusters.txt'))
        writeStringToFile(clasters_output, output_dir + 'clusters.txt')

        plt.subplot(111)

        # Black removed and is used for noise instead.
        unique_labels = set(labels)
        colors = plt.cm.Spectral(np.linspace(0, 1, len(unique_labels)))
        for k, col in zip(unique_labels, colors):
            if k == -1:
                # Black used for noise.
                col = 'k'

            class_member_mask = (labels == k)

            xy = X[class_member_mask & core_samples_mask]
            plt.plot(xy[:, 0], xy[:, 1], 'o', markerfacecolor=col,
                     markeredgecolor='k', markersize=14)

            xy = X[class_member_mask & ~core_samples_mask]
            plt.plot(xy[:, 0], xy[:, 1], 'o', markerfacecolor=col,
                     markeredgecolor='k', markersize=6)

        for label, x, y in zip(short_filenames, X[:, 0], X[:, 1]):
            plt.annotate(
                label,
                xy=(x, y), xytext=(-20, 20),
                textcoords='offset points', ha='right', va='bottom',
                # bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        plt.xticks(())
        plt.yticks(())
        plt.grid()


    def make_ward_clustering(self, short_filenames, input_texts):

        output_dir = self.output_dir + 'WARD/'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.signals.PrintInfo.emit("Расчет IDF...")
        idf_filename = output_dir + 'idf.csv'
        msg = self.calculate_and_write_idf(idf_filename, input_texts)
        self.signals.PrintInfo.emit(msg)

        vectorizer = CountVectorizer()
        X = vectorizer.fit_transform(input_texts)

        svd = TruncatedSVD(2)
        normalizer = Normalizer(copy=False)
        lsa = make_pipeline(svd, normalizer)
        X = lsa.fit_transform(X)

        ward = AgglomerativeClustering(n_clusters=self.ward_parameter_clusters_count, linkage='ward')
        predict_result = ward.fit_predict(X)
        print('predict_result:', predict_result)

        self.signals.PrintInfo.emit('\nПрогноз по документам:\n')

        clasters_output = ''
        for claster_index in range(max(predict_result)+1):
            clasters_output += ('Кластер ' + str(claster_index) + ':\n')
            for predict, document in zip(predict_result, short_filenames):
                if predict == claster_index:
                    clasters_output += ('  ' + str(document) + '\n')
            clasters_output += '\n'
        self.signals.PrintInfo.emit(clasters_output)
        self.signals.PrintInfo.emit('Сохранено в:' + str(output_dir + 'clusters.txt'))
        writeStringToFile(clasters_output, output_dir + 'clusters.txt')


        plt.subplot(111)
        colors = np.array([x for x in 'bgrcmykbgrcmykbgrcmykbgrcmyk'])
        colors = np.hstack([colors] * 20)
        plt.scatter(X[:, 0], X[:, 1], color=colors[predict_result].tolist(), s=50)


        for label, x, y in zip(short_filenames, X[:, 0], X[:, 1]):
            plt.annotate(
                label,
                xy=(x, y), xytext=(-20, 20),
                textcoords='offset points', ha='right', va='bottom',
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        plt.xticks(())
        plt.yticks(())
        plt.grid()
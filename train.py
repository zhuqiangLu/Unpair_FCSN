from keyFrameSelector import SK
from summaryDiscriminator import SD
from dataloader import get_dataloader
from utils import score_shot, knapsack
import torch.optim as optim
import torch.nn as nn
import config
import torch


class Trainer(object):

    def __init__(self, data_path, alpha, beta, n_class=2):
        self.train_loader = get_dataloader()

        self.SD = SD()
        self.opt_SD = optim.SGD(self.SD.parameters(), lr=config.SD_lr)
        self.SD_losses = list()

        self.SK = SK()
        self.opt_SK = optim.Adam(self.SD.parameters(), lr=config.SK_lr)
        self.SK_losses = list()

        self.device = torch.device("cuda:0" if (
            torch.cuda.is_available() and ngpu > 0) else "cpu")

        self.crit_adv = nn.BCELoss()

        self.epoch = config.epoch
        self.alpha = alpha
        self.beta = beta

    def crit_reconst(self, pred_sum, gt_sum):
        '''the expected dim of pred is [1, c, t]'''

        k = pred.shape(2)
        return torch.norm(pred_sum-gt_sum, dim=2).sum()/k

    def crit_div(self, pred):
        '''the expected dim of pred is [1, c, t]'''
        k = pred.shape(2)
        cos = nn.CosineSimilarity(dim=0)
        loss = torch.zeros([0])
        for i in range(k):
            for j in range(k):
                if i == j:
                    continue
                else:
                    loss += cos(pred[0, :, i], pred[0, :, j])
        return loss/(k*(k+1))

    def train_SD(self, fake_sum, real_sum):
        '''
            note that this method takes one sample at a time

            make sure the fake_sum are DETACHED from the generator net
        '''
        self.opt_SD.zero_grad()

        # train on real data
        pred_real = self.SD(real_sum)
        # as all frames belongs to the summary
        loss_real = self.crit_adv(pred_real, torch.ones(1, 1))
        loss_real.backward()

        # train on generated data
        pred_fake = self.SD(fake_sum)
        # as all frames are generated by SK
        loss_fake = self.crit_adv(pred_fake, torch.zeros(1, 1))
        loss_fake.backward()

        self.opt_SD.step()

        return loss_real+loss_fake, pred_real, pred_fake

    def train_SK(self, pred_scores, gt_scores, feature_vectors, beta):
        '''
            the expected shape of video(feacture vectors) is (N, C, T)

            Note that N should be 1 unless all T have the same value
        '''

        self.opt_SK.zero_grad()
        pred_sum, picks = self.SK(video)
        loss_adv = self.crit_adv(self.SD(pred_sum), torch.ones(
            1, 1)) + self.crit_reconst(pred_sum, feature_vectors[:, :, picks],) + self.crit_div(pred_sum)
        loss_adv.backward()
        self.opt_SK().step()
        return loss_adv, pred_sum, picks

    def eval(self, picks, video_info):
        gt_scores = video_info['gt_score'][()]  # (n, 1)

        pred_scores = np.zeros((gt_score.shape))  # (n, 1)
        pred_scores[picks, :] = 1

        cps = video_info['change_points'][()]  # (n_cp, 2)
        picks = video_info['picks'][()]  # (n_selected_frame, )
        n_frame_per_seg = video_info['n_frame_per_seg'][()]  # (n_cp, )

        gt_seg_scores = score_shot(
            cps, gt_scores, picks, n_frame_per_seg)  # (n_cp, )
        pred_seg_scores = score_shot(
            cps, pred_scores, picks, n_frame_per_seg)  # (n_cp, )

        # the length of the summary
        length = int(video_info['n_frame'][()] * 0.15)

        gt_seg_idx = knapsack(gt_seg_scores, n_frame_per_seg, length)
        pred_seg_idx = knapsack(pred_seg_scores, n_frame_per_seg, length)

    def train(self):

        for i in range(self.epoch):

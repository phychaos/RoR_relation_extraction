from dataloader import read_data
from tqdm import tqdm
import torch as tc
from models import models
import pdb
import os , sys
import math
from transformers.optimization import get_cosine_schedule_with_warmup , get_linear_schedule_with_warmup
from loss import loss_funcs
from generate import generate
from test import test
from utils.train_util import pad_sents , get_data_from_batch
from utils.scorer import get_f1
import fitlog
import pickle

fitlog.commit(__file__)

def load_data(C , logger):
	data_train , data_test , data_valid , relations, rel_weights = read_data(
		logger , 
		C.train_text_1 , C.train_rels_1 ,
		C.train_text_2 , C.train_rels_2 ,
		C.test_text  , C.test_rels ,
		C.valid_text , C.valid_rels ,
		C.dataset, C.rel_weight_smooth, C.rel_weight_norm,
	)

	return data_train , data_test , data_valid , relations, rel_weights

def train(C , logger , train_data , valid_data , relations , rel_weights , n_rel_typs , no_rel , ensemble_id = 0):	
	#----- determine some arguments -----
	assert len(rel_weights) == 7

	batch_numb = (len(train_data) // C.batch_size) + int((len(train_data) % C.batch_size) != 0)

	#----- get model and other training tools -----
	model = models[C.model](n_rel_typs = n_rel_typs , dropout = C.dropout).cuda()

	optimizer = tc.optim.Adam(params = model.parameters() , lr = C.lr)
	scheduler = get_cosine_schedule_with_warmup(
		optimizer = optimizer , 
		num_warmup_steps = C.n_warmup , 
		num_training_steps = batch_numb * C.epoch_numb , 
	)
	loss_func = loss_funcs[C.loss]

	#----- iterate each epoch -----

	best_epoch = -1
	best_macro_f1 = -1
	for epoch_id in range(C.epoch_numb):

		pbar = tqdm(range(batch_numb) , ncols = 70)
		avg_loss = 0
		for batch_id in pbar:
			#----- get data -----
			data = train_data[batch_id * C.batch_size : (batch_id+1) * C.batch_size]
			sents , ents , anss , data_ent = get_data_from_batch(data)

			#----- forward -----
			pred = model(sents , ents)
			loss = loss_func(pred , anss , ents , no_rel = no_rel , class_weight = rel_weights)

			#----- backward -----
			optimizer.zero_grad()
			loss.backward()
			optimizer.step()
			scheduler.step()

			#----- other activitis ----

			avg_loss += float(loss)
			fitlog.add_loss(value = float(loss) , step = epoch_id * batch_numb + batch_id , 
					name = "({0})train loss".format(ensemble_id))

			pbar.set_description_str("(Train)Epoch %d" % (epoch_id))
			pbar.set_postfix_str("loss = %.4f (avg = %.4f)" % ( float(loss) , avg_loss / (batch_id+1)))
		logger.log ("Epoch %d ended. avg_loss = %.4f" % (epoch_id , avg_loss / batch_numb))

		#----- valid -----
		micro_f1 , macro_f1 = test(
			C , logger , 
			valid_data , model , 
			relations  , rel_weights , no_rel , 
			epoch_id   , ensemble_id , 
		)

		if best_macro_f1 < macro_f1:
			best_epoch = epoch_id
			best_macro_f1 = macro_f1
			with open(C.tmp_file_name + ".model" , "wb") as fil:
				pickle.dump(model , fil)
			
		#	fitlog.add_best_metric(best_macro_f1 , name = "({0})macro f1".format(ensemble_id))


		model = model.train()


	if not C.no_valid:
		with open(C.tmp_file_name + ".model" , "rb") as fil:
			model = pickle.load(fil) #load best valid model

	logger.log("reloaded best model at epoch %d" % best_epoch)

	return model

if __name__ == "__main__":
	from config import C, logger

	#----- prepare data and some global variables -----
	data_train , data_test , data_valid , relations, rel_weights = load_data(C , logger)

	if C.rel_only: # no no_rel
		n_rel_typs , no_rel = len(relations) , -1
	else:
		n_rel_typs , no_rel = len(relations) + 1 , len(relations)
		rel_weights = rel_weights + [C.no_rel_weight]

	#----- train & test -----
	trained_models = []
	for i in range(C.ensemble_size):
		model = train(
			C , logger , 
			data_train , data_valid , 
			relations, rel_weights , n_rel_typs , no_rel , 
			ensemble_id = i , 
		)
		model = model.cpu()
		trained_models.append(model)

	#----- ensemble test -----
	micro_f1 , macro_f1 = test(
		C , logger , 
		data_test , trained_models , 
		relations , rel_weights , no_rel , 
		epoch_id = C.epoch_numb , ensemble_id = 'final', 
	)
	fitlog.add_best_metric(macro_f1 , name = "(ensembled)macro f1")

	#----- finish -----
	fitlog.finish()
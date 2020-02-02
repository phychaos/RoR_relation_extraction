import torch as tc

class TwoPhaseModel:
	'''
		generate only. do not train this.
	'''

	def __init__(self , binary_model , pos_only_model , no_rel_idx , threshold):
		self.binary_model = binary_model
		self.pos_only_model = pos_only_model

		self.no_rel = no_rel_idx
		self.threshold = threshold

	def forward(self , *pargs , **kwargs):

		with tc.no_grad():
			pred_binary = self.binary_model(*pargs , **kwargs)
			pred_psonly = self.pos_only_model(*pargs , **kwargs)

			pred_binary = tc.softmax(pred_binary , dim = -1)
			pred_psonly = tc.softmax(pred_psonly , dim = -1)

		bs , ne , ne , n_pos = pred_psonly.size()
		assert tuple(pred_binary.size()) == (bs , ne , ne , 2)

		pred_pos = (pred_binary[:,:,:,1] >= self.threshold).float().view(bs,ne,ne,1) # (bs,ne,ne) 1 for positive

		pred_no_rel = (1-pred_pos)
		pred_psonly = pred_psonly * pred_pos

		pred = tc.cat( [pred_psonly[:,:,:,:self.no_rel] , pred_no_rel , pred_psonly[:,:,:,self.no_rel:]] , dim = -1 )

		pred = pred + 1e-6 # 防止求loss的时候报NAN，虽然求loss没有意义

		return pred

	def __call__(self , *pargs , **kwargs):
		return self.forward(*pargs , **kwargs)

	@property
	def parameters(self): #for device deciding
		return self.binary_model.parameters

	def to(self , *pargs , **kwargs):
		self.binary_model  .to(*pargs , **kwargs)
		self.pos_only_model.to(*pargs , **kwargs)
		return self


	def eval(self):
		self.binary_model   = self.binary_model.eval()
		self.pos_only_model = self.pos_only_model.eval()
		return self
	def train(self):
		self.binary_model   = self.binary_model.train()
		self.pos_only_model = self.pos_only_model.train()
		return self


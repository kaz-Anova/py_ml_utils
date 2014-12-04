from sklearn.base import BaseEstimator, ClassifierMixin
import pandas as pd
import sys, tempfile, shlex, os, subprocess
sys.path.append('lib')
import xgboost as xgb
from pandas_extensions import *

_ftrl_default_path = 'utils/lib/tingrtu_ftrl.py'

class FTRLClassifier(BaseEstimator, ClassifierMixin):
  def __init__(self, column_names, alpha=0.15, beta=1.1, L1=1.1, L2=1.1, bits=23,  
                n_epochs=1,holdout=100,interaction=False, dropout=0.8, 
                sparse=False, seed=0):    
    self.column_names = column_names
    self.alpha = alpha
    self.beta = beta
    self.L1 = L1
    self.L2 = L2
    self.interaction = interaction 
    self.dropout = dropout
    self.bits = bits
    self.holdout = holdout
    self.n_epochs = n_epochs
    self.sparse=sparse
    self.seed=seed    
    self.tmpdir = 'tmpfiles'
    self._model_file = None
    self._train_file = None
    self._train_file_keep = False

  def fit(self, X, y, delay=True):
    train_file = self._get_train_file(X, y)
    if delay: 
      self._train_file = train_file
      self._train_file_keep = True
      return self

    self._train_file = None
    self._do_train_command(train_file)
    if not type(X) is str: os.remove(train_file)
    return self

  def predict(self, X): 
    return self.predict_proba(X)
  
  def predict_proba(self, X): 
    test_file = self._get_test_file(X)
    if self._train_file is not None:
      predictions_file = self._do_train_test_command(self._train_file, test_file)
      if not self._train_file_keep: os.remove(self._train_file)
    else:
      predictions_file = self._do_test_command(test_file)
      os.remove(self._model_file)
    if not type(X) is str: os.remove(test_file)    
    
    predictions = self._read_predictions(predictions_file)  
    os.remove(predictions_file)

    return predictions

  def _do_train_command(self, train_file):    
    self._model_file = self._get_tmp_file('model', 'model')
    cmd = 'pypy ' + _ftrl_default_path + ' train -t ' + train_file + \
      ' -o ' + self._model_file + ' --alpha ' + `self.alpha` + \
      ' --beta ' + `self.beta` + ' --L1 ' + `self.L1` + ' --L2 ' + `self.L2` + \
      ' --dropout ' + `self.dropout` + ' --bits ' + `self.bits` + \
      ' --n_epochs ' + `self.n_epochs` + ' --holdout ' + `self.holdout`
    if self.interaction: cmd += ' --interactions'
    if self.sparse: cmd += ' --sparse'
    self._make_subprocess(cmd)

  def _do_test_command(self, test_file):    
    predictions_file = self._get_tmp_file('predictions')
    cmd = 'pypy ' + _ftrl_default_path + \
      ' predict --test ' + test_file + ' -i ' + self._model_file + \
      ' -p ' + predictions_file
    self._make_subprocess(cmd)
    return predictions_file

  def _do_train_test_command(self, train_file, test_file):    
    predictions_file = self._get_tmp_file('predictions')
    cmd = 'pypy ' + _ftrl_default_path + ' train_predict -t ' + train_file + \
      ' --test ' + test_file + ' --alpha ' + `self.alpha` + \
      ' --beta ' + `self.beta` + ' --L1 ' + `self.L1` + ' --L2 ' + `self.L2` + \
      ' --dropout ' + `self.dropout` + ' --bits ' + `self.bits` + \
      ' --n_epochs ' + `self.n_epochs` + ' --holdout ' + `self.holdout` +\
      ' -p ' + predictions_file
    if self.interaction: cmd += ' --interactions'
    if self.sparse: cmd += ' --sparse'
    self._make_subprocess(cmd)
    return predictions_file

  def _read_predictions(self, predictions_file):
    predictions = pd.read_csv(predictions_file, compression='gzip', header=None, dtype='float')
    return predictions[predictions.columns[-1]].values

  def _get_train_file(self, X, y):
    if type(X) is str: return X    
    f = self._get_tmp_file('train')
    self._save_csv(f, X, y)
    return f

  def _get_test_file(self, X):
    if type(X) is str: return X
    f = self._get_tmp_file('test')
    self._save_csv(f, X)
    return f

  def _get_tmp_file(self, purpose, ext='csv.gz'):
    _, f = tempfile.mkstemp(dir=self.tmpdir, suffix=purpose + '.' + ext)
    os.close(_)
    return self.tmpdir + '/' + f.split('\\')[-1]    

  def _make_subprocess(self, command):    
    stdout = open('nul', 'w')
    stderr = sys.stderr

    print 'Running command: "%s"' % str(command)
    commands = shlex.split(str(command))
    result = subprocess.Popen(commands, 
        stdout=stdout, stderr=stderr, 
        close_fds=sys.platform != "win32", 
        universal_newlines=True, cwd='.')
    result.command = command

    if result.wait() != 0:
      raise Exception("pypy %d (%s) exited abnormally with return code %d" % \
        (result.pid, result.command, result.returncode))

    return result

  def _save_csv(self, out_file, X, opt_y=None):
    created_df = False
    if type(X) is not pd.DataFrame:      
      created_df = True
      X = pd.DataFrame(data=X, columns=self.column_names)
    if opt_y is not None: X['y'] = opt_y
    X.save_csv(out_file)
    if not created_df and opt_y is not None: X.remove('y')

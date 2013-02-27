from pylab import *
import tables
import cPickle
from scipy.optimize.optimize import fmin_cg, fmin_bfgs, fmin
from scipy.ndimage import filters, interpolation
from collections import Counter
from collections import defaultdict
from scipy.ndimage import measurements
from collections import Counter
import random as pyrandom
import improc
import mlinear
from toplevel import *
if 0:
    from scipy.spatial.distance import cdist
else:
    from ocrolib.distance import cdist

sidenote = "\t\t\t\t\t"

def method(cls):
    """Adds the function as a method to the given class."""
    import new
    def _wrap(f):
        cls.__dict__[f.func_name] = new.instancemethod(f,None,cls)
        return None
    return _wrap

###
### Helper classes.
###

class Err:
    def __init__(self,n=10000):
        self.n = n
        self.total = 0.0
        self.count = 0
    def add(self,x):
        l = 1.0/self.n
        self.total = (self.total*(1.0-l)+x*l)
        self.count += 1
    def value(self):
        return self.total

@checks(ndarray)
def make2d(data):
    """Convert any input array into a 2D array by flattening axes 1 and over."""
    if data.ndim==1: return array([data])
    if data.ndim==2: return data
    return data.reshape(data.shape[0],-1)

@checks(AFLOAT2,{int,NoneType},{int,NoneType})
def cshow(im,h=None,w=None):
    if h is None:
        h = w = int(sqrt(im.size))
    elif w is None:
        w=h
    # figsize(4,4)
    ion(); gray()
    imshow(im.reshape(h,w),cmap=cm.gray,interpolation='nearest')

def showgrid(l,h=None,w=None):
    # figsize(min(12,c),min(12,c)); gray()
    if h is None:
        h = w = int(sqrt(l[0].size))
    elif w is None:
        w=h
    ion()
    xticks([]); yticks([])
    n = len(l)
    c = int(sqrt(n))
    r = (n+c-1)//c
    # print r,c
    for i in range(n):
        subplot(r,c,i+1)
        imshow(l[i].reshape(h,w),cmap=cm.gray,interpolation='nearest')

###
### Dataset abstraction, useful for dealing with large
### data sets stored on disk (e.g., in HDF5 files).
###

class Dataset:
    """A wrapper for datdasets that allows individual items to
    be transformed using a feature extractor `f`, and subsets
    to be selected.  This somewhat insulates pattern recognition
    algorithms from the idiosyncracies of HDF5 tables and
    prevents to some degree accidentally loading too much data
    into memory at once."""
    def __init__(self,a,f=lambda x:x,subset=None,maxsize=None):
        if subset is None: subset = range(len(a))
        if maxsize is None: maxsize = len(a)
        subset = subset[:min(len(subset),maxsize)]
        self.a = a
        self.f = f
        self.subset = subset
    def __len__(self):
        return len(self.subset)
    def __getitem__(self,i):
        if type(i)==slice:
            return [self.f(self.a[self.subset[j]].ravel()) for j in range(i.start,i.stop,i.step or 1)]
        else:
            assert i>=0 and i<len(self)
            return self.f(self.a[self.subset[i]].ravel())
    def __iter__(self):
        for i in range(len(self)):
            yield self.a[self.subset[i]]

###
### probability distributions
###

@checks(AINT1)
def distribution(classes,n=-1):
    c = Counter(classes)
    if n<0: n = max(classes)+1
    p = zeros(n)
    p[c.keys()] = c.values()
    return p/maximum(0.1,sum(p))

###
### vector "sorting" and selecting
### 

def minsert(x,l):
    if len(l)<2:
        return l+[x]
    dists = array(cdist([x],l))[0]
    dists2 = dists+roll(dists,-1)
    i = argmin(dists)
    return l[:i]+[x]+l[i:]

def vecsort(l):
    l = list(l)
    result = l[:3]
    for v in l[3:]:
        result = minsert(v,result)
    return result

def rselect(data,n,s=1000,f=0.99):
    N = len(data)
    l = pyrandom.sample(data,1)
    while len(l)<n:
        if len(l)%100==0: print len(l)
        vs = pyrandom.sample(data,s)
        ds = cdist(l,vs)
        ds = amin(ds,axis=0)
        js = argsort(ds)
        j = js[int(f*len(js))]
        l = minsert(vs[j],l)
    return l

###
### PCA
###

@checks(DATASET(fixedshape=1,vrank=1),True,min_k=RANGE(2,100000),whiten=BOOL)
def pca(data,k,min_k=2,whiten=0):
    """Computes a PCA and a whitening.  The number of
    components can be specified either directly or as a fraction
    of the total sum of the eigenvalues (k in [0...1]).
    The function returns
    the transformed data, the mean, the eigenvalues, and 
    the eigenvectors."""
    n,d = data.shape
    assert k>=0
    assert k<=d and k<=n
    mean = average(data,axis=0).reshape(1,d)
    data = data - mean.reshape(1,d)
    cov = dot(data.T,data)/n
    evals,evecs = linalg.eigh(cov)
    top = argsort(-evals)
    if k<1:
        fracs = add.accumulate(sorted(abs(evals),reverse=1))
        kd = find(fracs>=k*fracs[-1])[0]
        # print sidenote+"pca",kd,k,len(evals)
        k = maximum(min_k,kd)
    evals = evals[top[:k]]
    evecs = evecs.T[top[:k]]
    assert evecs.shape==(k,d)
    ys = dot(evecs,data.T)
    assert ys.shape==(k,n)
    if whiten: ys = dot(diag(sqrt(1.0/evals)),ys)
    return (ys.T,mean.ravel(),evals,evecs)


class PCA:
    """A class wrapper for the pca function that makes it a little easier
    to use in some contexts."""
    def __init__(self,k):
        self.k = k
    def fit(self,data):
        data = data.reshape(len(data),-1)
        _,mu,evals,P = pca(data,self.k)
        self.mu = mu
        self.evals = evals
        self.P = P
    def transform(self,data):
        data = data.reshape(len(data),-1)
        ys = dot(data-self.mu[newaxis,:],self.P.T)
        return ys
    def residual(self,data):
        data = data.reshape(len(data),-1)
        return sum(data**2,axis=1)-sum(self.transform(data)**2,axis=1)
    def inverse_transform(self,data):
        data = data.reshape(len(data),-1)
        xs = dot(out,self.P)+self.mu[newaxis,:]
        return xs

###
### k-means clustering
###

@checks(DATASET(fixedshape=1,vrank=1),RANGE(2,100000),maxiter=RANGE(0,10000000))
def kmeans(data,k,maxiter=100):
    """Regular k-means algorithm.  Computes k means from data."""
    centers = array(pyrandom.sample(data,k),'f')
    last = -1
    for i in range(maxiter):
        mins = argmin(cdist(data,centers),axis=1)
        if (mins==last).all(): break
        for i in range(k):
            if sum(mins==i)<1: 
                centers[i] = pyrandom.sample(data,2)[0]
            else:
                centers[i] = average(data[mins==i],axis=0)
        last = mins
    return centers

class Kmeans:
    """Perform k-means clustering."""
    def __init__(self,k,maxiter=100,npk=1000,verbose=0):
        self.k = k
        self.maxiter = maxiter
        self.verbose = verbose
    def fit(self,data):
        self.centers = kmeans(data,self.k,maxiter=self.maxiter)
    def centers(self):
        return self.centers
    def center(self,i):
        return self.centers[i]
    def predict(self,data,n=0):
        nb = knn(ys,self.Pcenters,max(1,n))
        if n==0:
            return nb[:,0]
        else:
            return nb

@checks(DATASET(fixedshape=1,vrank=1),RANGE(0,100000),RANGE(0,10000),maxiter=RANGE(0,10000000),\
        npk=RANGE(2,100000),maxsample=RANGE(3,1e9),min_norm=RANGE(0.0,1000.0))
def pca_kmeans(data,k,d,min_d=3,maxiter=100,npk=1000,verbose=0,maxsample=200000,min_norm=1e-3):
    assert len(data)>=1
    n = min(len(data),k*npk,maxsample)
    if n<len(data):
        # if verbose: print sidenote+"pca_kmeans sampling",n,"samples"
        sample = pyrandom.sample(data,n)
    else:
        sample = list(data)
    sample = [v for v in sample if norm(v)>=min_norm]
    sample = array(sample)
    assert len(sample)>=1
    sample = sample.reshape(len(sample),-1)
    if verbose: print sidenote+"pca",len(sample),"d",d
    ys,mu,evals,evecs = pca(sample,d,min_k=min_d)
    if verbose: print sidenote+"kmeans",len(sample),"k",k,"d",ys.shape
    km = kmeans(ys,k)
    if verbose:
        print sidenote+"km",km.shape,"evecs",evecs.shape,"mu",mu.shape
    del ys; del sample
    return km,evecs,mu
    
def pca_kmeans0(data,k,d=0.9,**kw):
    """Performs kmeans in PCA space, but otherwise looks like regular
    k-means (i.e., it returns the centers in the original space).
    This is useful both for speed and because it tends to give better results
    than regular k-means."""
    km,evecs,mu = pca_kmeans(data,k,d,**kw)
    return dot(km,evecs)+mu[newaxis,:]

@checks(AFLOAT2,AFLOAT2,int,chunksize=RANGE(1,1000000000))
def knn(data,protos,k,chunksize=1000,threads=-1):
    result = []
    for i in range(0,len(data),chunksize):
        block = data[i:min(i+chunksize,len(data))]
        if type(block)!=ndarray: block = array(block)
        ds = cdist(block,protos,threads=threads)
        js = argsort(ds,axis=1)
        result.append(js[:,:k])
    return vstack(result)

def protosets(nb,k):
    """For a list of nearest neighbors to k prototypes,
    compute the set belonging to each prototype."""
    if k is None: k = amax(nb)+1
    psets = [set() for _ in range(k)]
    for i,v in enumerate(nb):
        psets[v].add(i)
    return psets

class PcaKmeans:
    """Perform PCA followed by k-means.
    This code is able to deal with Datasets as input, not just arrays."""
    def __init__(self,k,d,min_d=3,maxiter=100,npk=1000,verbose=0,threads=1):
        self.k = k
        self.d = d
        self.min_d = min_d
        self.maxiter = maxiter
        self.npk = npk
        self.verbose = verbose
    def fit(self,data):
        self.Pcenters,self.P,self.mu = \
            pca_kmeans(data,self.k,self.d,min_d=self.min_d,
                       maxiter=self.maxiter,npk=self.npk,verbose=self.verbose)
        self.Pcenters = array(vecsort(self.Pcenters))
    def centers(self):
        return dot(self.Pcenters,self.P)+self.mu
    def center(self,i):
        return dot(self.Pcenters[i],self.P)+self.mu
    def dist1(self,x):
        y = dot(x.ravel()-self.mu.ravel(),self.P.T)
        return sqrt(norm(x.ravel()-self.mu.ravel())**2-norm(y)**2)
    def predict1(self,x,threads=1):
        # We always use multiple threads during training, but
        # only one thread by default for prediction (since
        # prediction is usually run in parallel for multiple
        # lines)
        y = dot(x.ravel()-self.mu.ravel(),self.P.T)
        c = knn(y.reshape(1,-1),self.Pcenters,1,threads=threads)
        return c[0][0]
    def predict(self,data,n=0,threads=1):
        if type(data)==ndarray:
            # regular 2D array code
            data = data.reshape(len(data),-1)
            ys = dot(data-self.mu,self.P.T)
            nb = knn(ys,self.Pcenters,max(1,n),threads=threads)
        else:
            # for datasets (and other iterables), use a slower, per-row routine
            nb = []
            for i,x in enumerate(data):
                if self.verbose:
                    if i%100000==0: print sidenote+"PcaKmeans.predict",i
                nb.append(self.predict1(x))
            nb = array(nb)
        if n==0:
            return nb[:,0]
        else:
            return nb

###
### A tree vector quantizer.
###
### TODO:
### - implement pruning based on distortion measure
###

class HierarchicalSplitter:
    def __init__(self,**kw):
        self.maxsplit = 100
        self.maxdepth = 2
        self.d = 0.90
        self.min_d = 3
        self.verbose = 0
        self.depth = 0
        self.splitsize = 10000
        self.targetsize = 1000
        self.offsets = None
        self.splitter = None
        self.subs = None
        self.quiet = 0
        self.extractor = None
        assert set(kw.keys())<set(dir(self))
        self.__dict__.update(kw)
        if "depth" in kw: del kw["depth"]
        self.kw = kw
        self.offsets = None
    def fit(self,data,offset=0):
        assert len(data)>=3
        if "extractor" in dir(self) and self.extractor is not None:
            data = Dataset(data,f=self.extractor)
        k = maximum(2,minimum(len(data)//self.targetsize,self.maxsplit))
        d = self.d
        if not self.quiet: print "\t"*self.depth,"pcakmeans",len(data),"k",k,"d",d
        self.splitter = PcaKmeans(k,d)
        self.splitter.fit(data)
        if not self.quiet: print "\t"*self.depth,"predicting",len(data),len(data[0])
        nb = self.splitter.predict(data,n=1)
        sets = protosets(nb,k)
        self.subs = [None]*k
        self.offsets = []
        for s,subset in enumerate(sets):
            self.offsets.append(offset)
            if self.verbose:
                print "\t"*self.depth,"bucket",s,"of",k,"len",len(subset),"offset",offset
            if self.depth>=self.maxdepth or len(subset)<self.splitsize:
                offset += 1
            else:
                sub = HierarchicalSplitter(depth=self.depth+1,**self.kw)
                subdata = [data[i] for i in sets[s]]
                if len(subdata)>=3:
                    offset = sub.fit(subdata,offset=offset)
                    self.subs[s] = sub
                else:
                    print "WARNING: empty split"
        self.offsets.append(offset)
        return offset
    def predict1(self,v):
        if "extractor" in dir(self) and self.extractor is not None:
            v = self.extractor(v)
        s = self.splitter.predict(v.reshape(1,-1))[0]
        if self.subs[s] is None:
            return self.offsets[s]
        else:
            if self.subs[s] is None: return -1
            return self.subs[s].predict1(v)
    def predict(self,data):
        return array([self.predict1(v) for v in data],'i')
    def nclusters(self):
        return self.offsets[-1]
    def center(self,v):
        """Returns the cluster number and cluster center associated 
        with this vector"""
        s = self.splitter.predict(v.reshape(1,-1))[0]
        if self.subs[s] is None:
            result = (self.offsets[s],self.splitter.center(s))
        else:
            result = self.subs[s].center(v)
        print result
        return result
    
###
### A couple of trivial classifiers and cost models, used for testing.
###

class TrivialCmodel:
    """Classify using just the prior information."""
    def __init__(self,limit=5):
        self.limit = limit
    def fit(self,data,classes):
        self.counter = Counter(classes)
    def coutputs(self,v):
        n = sum(self.counter.values())
        return [(k,c*1.0/n) for k,n in self.counter.most_common(self.limit)]

class TrivialCostModel:
    """Here, cost is simply Euclidean distance from the mean of the bucket.
    This corresponds to a unit covariance matrix."""
    def fit(self,data):
        data = data.reshape(len(data),-1)
        self.avg = mean(data,axis=0)
    def cost(self,v):
        return norm(self.avg-v)

###
### Logistic character classifier
###

class LogisticCmodel:
    def __init__(self,d=0.9,min_d=2,linear=0,l=1e-4):
        self.d = d
        self.min_d = min_d
        self.linear = linear
        self.l = l
    def fit(self,data,classes):
        self.reverse = sorted(Counter(classes).keys())
        self.forward = { k:i for i,k in enumerate(self.reverse) }
        outputs = array([self.forward[c] for c in classes],'i')
        targets = zeros((len(data),len(self.reverse)),'f')
        for i,c in enumerate(outputs): targets[i,c] = 1
        (ys,mu,vs,tr) = pca(make2d(data),k=self.d,min_k=self.min_d)
        ys = c_[ones(len(ys)),ys]
        if self.linear:
            M2 = linalg.lstsq(ys,targets)[0]
        else:
            M2 = mlinear.logreg_l2_fp(ys,targets,l=self.l)
        b = M2[0,:]
        M = M2[1:,:]
        self.R = dot(M.T,tr)
        self.r = b-dot(self.R,mu.ravel())
    def coutputs(self,v,geometry=None):
        assert v.ndim==1
        pred = dot(v,self.R.T)+self.r
        if not self.linear: pred = mlinear.sigmoid(pred)
        return sorted(zip(self.reverse,pred),key=lambda x:-x[1])

# obsolete, just for backwards compatibility

def normalizer_none(v):
    return v.ravel()
def normalizer_normal(v):
    return improc.classifier_normalize(v)

###
### Overall binning classifier.
###

class LocalCmodel:
    def __init__(self,splitter):
        self.splitter = splitter
        self.nclusters = splitter.nclusters()
        self.cshape = None
        self.cmodels = [None]*self.nclusters
    def split1(self,v):
        return self.splitter.predict(v.reshape(1,-1))[0]
    def split1(self,v):
        return self.splitter.predict(v.reshape(1,-1))[0]
    def setCmodel(self,i,cmodel):
        """We leave the training of the individual buckets
        to code outside the class, since it is often parallelized
        and complicated.  All that we care about for classification
        is that we have a good cmodel for each bucket."""
        self.cmodels[i] = cmodel
    def coutputs(self,v,geometry=None,prenormalized=0):
        v = v.ravel()
        # after normalization, character sizes need to be consistent
        if self.cshape is None: self.cshape=v.shape
        else: assert self.cshape==v.shape
        # now split and predict
        i = self.splitter.predict1(v)
        if i<0: return []
        if self.cmodels[i] is None: return []
        return self.cmodels[i].coutputs(v,geometry=geometry)



class ModelWithExtractor:
    def __init__(self,model,extractor):
        self.model = model
        self.extractor = extractor
    def fit(self,data,classes):
        transformed = [self.extractor(v) for v in data]
        self.model.fit(transformed,classes)
    def coutputs(self,v,geometry=None,prenormalized=0):
        transformed = self.extractor(v)
        return self.coutputs(transformed)

class Extractor0:
    def __init__(self,alpha=0.5,dsigma=1.0,spread=0,tsize=(32,32)):
        assert alpha>=0.0 and alpha<=1.0
        assert dsigma>=0.0 and dsigma<=100.0
        assert spread>=0 and spread<=100 and type(spread)==int
        self.alpha = alpha
        self.dsigma = dsigma
        self.spread = spread
        self.tsize = tsize
    def __call__(self,image):
        if image.ndim==1:
            image = image.reshape(*self.tsize)
        left = 0.0+image[:,0]
        image[:,0] = 0
        deriv = filters.gaussian_gradient_magnitude(image,self.dsigma,mode='constant')
        if self.spread>0: deriv = filters.maximum_filter(image,(self.spread,self.spread))
        deriv /= 1e-6+amax(deriv)
        result = self.alpha*deriv + (1.0-self.alpha)*image
        result[:,0] = left
        return result

class Grad0Model(ModelWithExtractor):
    def __init__(self,mparams,eparams):
        ModelWithExtractor.__init__(self,LocalCModel(**mparams),Extractor0(**eparams))

class Extractor1:
    def __init__(self,alpha=0.5,dsigma=1.0,spread=3,buckets=2,tsize=(32,32)):
        assert alpha>=0.0 and alpha<=1.0
        assert dsigma>=0.0 and dsigma<=100.0
        assert spread>=0 and spread<=100 and type(spread)==int
        self.alpha = alpha
        self.dsigma = dsigma
        self.spread = spread
        self.buckets = buckets
        self.tsize = tsize
    def __call__(self,image):
        if image.ndim==1:
            image = image.reshape(*self.tsize)
        left = 0.0+image[:,0]
        image[:,0] = 0
        dy = filters.gaussian_filter(image,self.dsigma,order=(1,0),mode='constant')
        dx = filters.gaussian_filter(image,self.dsigma,order=(0,1),mode='constant')
        nb = self.buckets
        deriv = zeros(image.shape)
        for b,alpha in enumerate(linspace(0,pi,nb+1)):
            d = cos(alpha)*dx+sin(alpha)*dy
            dhi = filters.maximum_filter(d,self.spread)
            dlo = filters.maximum_filter(-d,self.spread)
            deriv[::2,b::nb] = maximum(0,dhi[::2,b::nb])
            deriv[1::2,b::nb] = maximum(0,dlo[1::2,b::nb])
        deriv /= 1e-6+amax(deriv)
        result = self.alpha*deriv + (1.0-self.alpha)*image
        result[:,0] = left
        return result

class Grad1Model(ModelWithExtractor):
    def __init__(self,mparams,eparams):
        ModelWithExtractor.__init__(self,LocalCModel(**mparams),Extractor1(**eparams))

class Extractor2:
    def __init__(self,alpha=0.0,dsigma=1.0,p=3.0,buckets=4,dzoom=0.5,spread=5,tsize=(32,32)):
        assert alpha>=0.0 and alpha<=1.0
        assert dsigma>=0.0 and dsigma<=100.0
        self.alpha = alpha
        self.dsigma = dsigma
        self.spread = spread
        self.buckets = buckets
        self.dzoom = dzoom
        self.tsize = tsize
        self.p = p
    def __call__(self,image):
        if image.ndim==1:
            image = image.reshape(*self.tsize)
        left = 0.0+image[:,0:1]
        image[:,0] = 0
        dy = filters.gaussian_filter(image,self.dsigma,order=(1,0),mode='constant')
        dx = filters.gaussian_filter(image,self.dsigma,order=(0,1),mode='constant')
        nb = self.buckets
        dzoom = self.dzoom
        derivs = []
        derivs.append(interpolation.zoom(left,(dzoom,1)))
        for b,alpha in enumerate(linspace(0,pi,nb+1)[:-1]):
            d = cos(alpha)*dx+sin(alpha)*dy
            dhi = filters.maximum_filter(maximum(d,0),self.spread)**self.p
            dhi = (1-self.alpha)*dhi+self.alpha*image
            derivs.append(interpolation.zoom(dhi,dzoom))
            dlo = filters.maximum_filter(maximum(-d,0),self.spread)**self.p
            dlo = (1-self.alpha)*dlo+self.alpha*image
            derivs.append(interpolation.zoom(dlo,dzoom))
        result = hstack(derivs)
        result /= amax(result)
        return result

class Grad2Model(ModelWithExtractor):
    def __init__(self,mparams,eparams):
        ModelWithExtractor.__init__(self,LocalCModel(**mparams),Extractor2(**eparams))

# need IPCA without covariance matrix
# maybe sectioned PCA



################################################################
### utility functions for parallelizing prediction and character
### classification (the overhead of this is too large to use
### it at a per-line level, but it is useful during training)
################################################################

import multiprocessing
import common

def datachunks(data,model=None,chunksize=1000):
    for i in range(0,len(data),chunksize):
        j = min(i+chunksize,len(data))
        block = data[i:j]
        if type(block)!=ndarray: block = array(block,'float32')
        yield i,j,block,model

def coutputs_chunk(job):
    i,j,block,model = job
    outputs = [model.coutputs(v) for v in block]
    return i,j,outputs

def parallel_coutputs(model,data,parallel=multiprocessing.cpu_count(),verbose=1):
    results = [None]*len(data)
    for i,j,outs in common.parallel_map(coutputs_chunk,datachunks(data,model=model),parallel=parallel):
        if verbose: print "parallel_coutputs",i,j,"(%d)"%parallel
        for k in range(j-i): results[i+k] = outs[k]
    return results

def predict_chunk(job):
    i,j,block,model = job
    return i,j,model.predict(block)

def parallel_predict(model,data,parallel=multiprocessing.cpu_count(),verbose=1):
    results = [None]*len(data)
    for i,j,outs in common.parallel_map(predict_chunk,datachunks(data,model=model),parallel=parallel):
        if verbose: print "parallel_predict",i,j,"(%d)"%parallel
        for k in range(j-i): results[i+k] = outs[k]
    return results


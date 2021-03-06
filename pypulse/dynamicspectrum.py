'''
Michael Lam 2015

To do: grid: set clim such that 0 is white, not blue,mask data,add zorder
'''


import numpy as np
import numpy.ma as ma
import pypulse.utils as u
import pypulse.functionfit as ffit
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from scipy.signal import fftconvolve
import scipy.optimize as optimize

import sys
if sys.version_info.major == 2:
    fmap = map    
elif sys.version_info.major == 3:
    fmap = lambda x,*args: list(map(x,*args))
    xrange = range


class DynamicSpectrum:
    def __init__(self,data,offdata=None,errdata=None,mask=None,F=None,T=None,extras=None,verbose=True):
        self.verbose=verbose
        if type(data) == type(""):
            name = data
            self.load(data)
            return
#            self.extras = dict()
#            self.extras['filename'] = data
        else:            
            self.data = data
        #check if 1d array
        if len(np.shape(self.data))>=1: #why==?????

            self.offdata = offdata
            self.errdata = errdata
            self.mask = mask
            self.F = F#these are the edges
            self.T = T
            self.Fcenter = None
            self.Tcenter = None
            self.dF = None
            self.dT = None
            if F is not None:
                d = np.diff(self.F)
                self.Fcenter = d/2.0 + self.F[:-1]
                self.dF = np.mean(d)
            if T is not None:
                d = np.diff(self.T)
                self.Tcenter = d/2.0 + self.T[:-1]
                self.dT = np.mean(d)
            if extras is None:
                self.extras = dict()
            else:
                self.extras = extras

        # Pre-define variables
        self.baseline_removed = False
        self.acf = None
        self.ss = None


    def getValue(self,f,t,df=1,dt=1,err=False,index=False):
        '''
        Returns value of dynamic spectrum
        if index==False, f,t are values to search for
        '''
        if index or self.F is None or self.T is None:
            if err:
                return self.errdata[f,t]
            return self.data[f,t]
        else:
            indsF = np.where(np.abs(self.Fcenter-f) <= df)[0]
            indsT = np.where(np.abs(self.Tcenter-t) <= dt)[0]
            if len(indsF)==0 or len(indsT)==0:
                return None
            if err:
                data = self.errdata
            else:
                data = self.data            
            total=0
            N=0
            for indF in indsF:
                for indT in indsT:
                    total+=data[indF,indT]
                    N+=1
            return total/float(N)


    def remove_baseline(self,function="gaussian",redo=False):
        """
        Attempts to remove the baseline amplitude from the dynamic spectrum
        """
        if redo == False and self.baseline_removed == True:
            return self
        flatdata = self.data.flatten()
        interval = np.power(10,np.floor(np.log10(np.ptp(flatdata/100)))) #~100 divisions, but bins to an even power of 10
        center,hist = u.histogram(flatdata,interval=interval)

        if function == "gaussian":
            p1,err = ffit.gaussianfit(center,hist)
            y = ffit.funcgaussian(p1,center)
            peak = center[np.argmax(y)]
            
        elif function == "simple_DISS":
            area = np.trapz(hist,x=center)
            shift = -np.min(center)+1.0
            x = center + shift
            y = np.array(hist,dtype=np.float)/area
            p1,err = ffit.simpleDISSpdffit(x,y)
            y1 = ffit.funcsimpleDISSpdf(p1,x)*area
            peak = center[np.argmax(y1)]
        else:
            peak = 0.0

        self.data -= peak
        self.baseline_removed = True
        return self
        
    def acf2d(self,remove_baseline=True,speed='fast',mode='full'):
        """
        Calculate the two-dimensional auto-correlation function of the dynamic spectrum
        """
        data = self.getData(remove_baseline=remove_baseline)

        # Have if statement to apply mask: set ones in the norm to 0.0

        ones = np.ones(np.shape(data))
        norm = fftconvolve(ones,np.flipud(np.fliplr(ones)),mode=mode)
        acf = fftconvolve(data,np.flipud(np.fliplr(data)),mode=mode)/norm


        # Replace the central noise spike with that of the next highest of its neighbors
        acfshape = np.shape(acf)
        centerrind = acfshape[0]//2
        centercind = acfshape[1]//2
        acf[centerrind,centercind] = 0.0
        acf[centerrind,centercind] = np.max(acf[centerrind-1:centerrind+2,centercind-1:centercind+2])

        self.acf = acf
        return acf
            
            

        #return u.acf2d(self.data,speed=speed,mode=mode) #do more here

    def secondary_spectrum(self,remove_baseline=True,log=False):
        data = self.getData(remove_baseline=remove_baseline)

        ss = np.abs(np.fft.fftshift(np.fft.fft2(data)))**2

        if log:
            ss = np.log10(ss)

        self.ss = ss
        return ss

    # allow for simple 1D fitting
    def scintillation_parameters(self,plotbound=1.0,maxr=None,maxc=None,savefig=None,show=True,full_output=False):
        if self.acf is None:
            self.acf2d()
        if self.dT is None:
            dT = 1
        else:
            dT = self.dT
        if self.dF is None:
            dF = 1
        else:
            dF = self.dF


        acfshape = np.shape(self.acf)
        centerrind = acfshape[0]//2
        centercind = acfshape[1]//2
            
        # Look for the central peak in the ACF

        MIN = np.min(self.acf) 
        if MIN < 0: #The min value is approximately from a gaussian distribution
            MIN = np.abs(MIN)
        else:
            #center,hist = u.histogram(acf.flatten(),interval=0.001) #relies on 0.001
            #MIN = center[np.argmax(hist)]
            MIN = u.RMS(self.acf.flatten())
        if maxr is None:
            rslice = self.acf[centerrind:,centercind]
            maxr = np.where(rslice<=MIN)[0][0]
        if maxc is None:
            cslice = self.acf[centerrind,centercind:]
            maxc = np.where(cslice<=MIN)[0][0]

        plotacf = self.acf[centerrind-plotbound*maxr+1:centerrind+plotbound*maxr,centercind-plotbound*maxc+1:centercind+plotbound*maxc+1]

        
        params, pcov = ffit.fitgaussian2d(plotacf) #pcov already takes into account s_sq issue
        SHAPE = np.shape(plotacf)

        fit = ffit.gaussian2d(*params)
        amplitude,center_x,center_y,width_x,width_y,rotation,baseline = params
        if self.verbose:
            paramnames = ["amplitude","center_x","center_y","width_x","width_y","rotation","baseline"]
            if pcov is not None:
                paramerrors = np.sqrt(np.diagonal(pcov))
            else:
                paramerrors = np.zeros_like(params)
            for i,param in enumerate(params):
                print("%s: %0.2e+/-%0.2e"%(paramnames[i],param,paramerrors[i]))
                

        #Solve for scintillation parameters numerically
        
        try:
            delta_t_d = (optimize.brentq(lambda y: fit(SHAPE[0]//2,y)-baseline-amplitude/np.e,(SHAPE[1]-1)//2,SHAPE[1]*2)-(SHAPE[1]-1)//2)*dT #FWHM test
            if self.verbose:
                print("delta_t_d %0.3f minutes"%delta_t_d)
        except ValueError:
            if self.verbose:
                print("ERROR in delta_t_d")
            delta_t_d = SHAPE[1]*dT
        if pcov is not None:
            err_t_d = paramerrors[3]*dT #assume no rotaton for now
        else:
            err_t_d = None

        try:
            delta_nu_d = (optimize.brentq(lambda x: fit(x,SHAPE[1]//2)-baseline-amplitude/2.0,(SHAPE[0]-1)//2,SHAPE[0])-(SHAPE[0]-1)//2)*dF
            if self.verbose:
                print("delta_nu_d %0.3f MHz"%delta_nu_d)
        except ValueError:
            if self.verbose:
                print("ERROR in delta_nu_d")
            delta_nu_d = SHAPE[0]*dF
        if pcov is not None:
            err_nu_d = paramerrors[4]*dF #assume no rotaton for now
        else:
            err_nu_d = None


        err_rot = paramerrors[5]



        if self.verbose:
            print("dnu/dt %0.3f MHz/min" % ((dF/dT)*np.tan(rotation)))#((dF/dT)*np.tan(rotation))

        if show or savefig is not None:
            fig = plt.figure()
            ax = fig.add_subplot(211)
            u.imshow(self.data)
            ax = fig.add_subplot(212)

            u.imshow(plotacf)
            plt.colorbar()
            levels = (amplitude*np.array([1.0,0.5,1.0/np.e]))+baseline
            levels = (amplitude*np.array([0.5]))+baseline
            print(levels)

            ax.contour(fit(*np.indices(plotacf.shape)),levels, colors='k')
            #ax.set_xlim(len(xs)-20,len(xs)+20)
            #ax.set_ylim(len(ys)-10,len(ys)+10)
            if savefig is not None:
                plt.savefig(savefig)
            if show:
                plt.show()
        if full_output:
            return delta_t_d,err_t_d,delta_nu_d,err_nu_d,rotation,err_rot
        return delta_t_d,delta_nu_d,rotation



    def imshow(self,err=False,cbar=False,ax=None,show=True,border=False,ZORDER=0,cmap=cm.binary,alpha=True,cdf=True):
        """
        Basic plotting of the dynamic spectrum
        """
        if err:
            spec = self.errdata
        else:
            spec = self.data
        T=self.T
        if self.T is None:
            if self.Tcenter is None:
                T = np.arange(len(spec))
            else:
                T = self.Tcenter
        F=self.F
        if self.F is None:
            if self.Fcenter is None:
                F = np.arange(len(spec[0]))
            else:
                F = self.Fcenter
        #cmap = cm.binary#jet
        if alpha:
            cmap.set_bad(alpha=0.0)


        if alpha: #do this?
            for i in range(len(spec)):
                for j in range(len(spec[0])):
                    if spec[i,j] <= 0.0:# or self.errdata[i][j]>3*sigma:
                        spec[i,j] = np.nan
        
        minT = T[0]
        maxT = T[-1]
        minF = F[0]
        maxF = F[-1]


        if cdf:
            xcdf,ycdf = u.ecdf(spec.flatten())
            low,high = u.likelihood_evaluator(xcdf,ycdf,cdf=True,values=[0.01,0.99])
            for i in range(len(spec)):
                for j in range(len(spec[0])):
                    if spec[i,j] <= low:
                        spec[i,j] = low
                    elif spec[i,j] >= high:
                        spec[i,j] = high


#        print inds
#        raise SystemExit
#        spec[inds] = np.nan
        cax=u.imshow(spec,ax=ax,extent = [minT,maxT,minF,maxF],cmap=cmap,zorder=ZORDER)

        #border here?
        if border:# and self.extras['name']!='EFF I':
            plt.plot([T[0],T[-1]],[F[0],F[0]],'0.50',zorder=ZORDER+0.1)
            plt.plot([T[0],T[-1]],[F[-1],F[-1]],'0.50',zorder=ZORDER+0.1)
            plt.plot([T[0],T[0]],[F[0],F[-1]],'0.50',zorder=ZORDER+0.1)
            plt.plot([T[-1],T[-1]],[F[0],F[-1]],'0.50',zorder=ZORDER+0.1)


        if cbar:
            plt.colorbar(cax)
        #im.set_clim(0.0001,None)
        if show:
            plt.show()

        return ax


    def load(self,filename):
        """
        Load the dynamic spectrum from a .npz file
        """
        if self.verbose:
            print("Dynamic Spectrum: Loading from file: %s" % filename)
        x = np.load(filename)
        for key in x.keys():
            exec("self.%s=x['%s']"%(key,key))
        exec("self.extras = dict(%s)"%self.extras)
        #Convert array(None) to None
        if self.offdata is not None and len(np.shape(self.offdata))==0:
            self.offdata = None
        if self.errdata is not None and len(np.shape(self.errdata))==0:
            self.errdata = None
        if self.mask is not None and len(np.shape(self.mask))==0:
            self.mask = None


        x.close()
        return

    def save(self,filename):
        """
        Save the dynamic spectrum to a .npz file
        """
        if self.verbose:
            print("Dynamic Spectrum: Saving to file: %s" % filename)
        np.savez(filename,data=self.data,offdata=self.offdata,errdata=self.errdata,mask=self.mask,F=self.F,T=self.T,Fcenter=self.Fcenter,Tcenter=self.Tcenter,baseline_removed=self.baseline_removed,acf=self.acf,ss=self.ss,extras=self.extras)
        return

        
    # Must be in time order!
    def add(self,ds,axis='T'):
        """
        Concatenates another dynamic spectrum with this one
        """
        if axis=='T':
            self.T = np.concatenate((self.T,ds.T))
            if len(np.shape(ds.data))==1:
                ds.data = np.reshape(ds.data,[len(ds.data),1])
                if ds.offdata is not None:
                    ds.offdata = np.reshape(ds.offdata,[len(ds.offdata),1])
                if ds.errdata is not None:
                    ds.errdata = np.reshape(ds.errdata,[len(ds.errdata),1])
                if ds.mask is not None:
                    ds.mask = np.reshape(ds.mask,[len(ds.mask),1])


            self.data = np.hstack((self.data,ds.data))
            #if statements
            if self.offdata is None and ds.offdata is None:
                self.offdata = None
            else:
                if self.offdata is None and ds.offdata is not None:
                    self.offdata = np.zeros(np.shape(self.data))
                elif self.offdata is not None and ds.offdata is None:
                    ds.offdata = np.zeros(np.shape(ds.data))
                self.offdata = np.hstack((self.offdata,ds.offdata))
            if self.errdata is None and ds.errdata is None:
                self.errdata = None
            else:
                if self.errdata is None and ds.errdata is not None:
                    self.errdata = np.zeros(np.shape(self.data))
                elif self.errdata is not None and ds.errdata is None:
                    ds.errdata = np.zeros(np.shape(ds.data))
                self.errdata = np.hstack((self.errdata,ds.errdata))
            if self.mask is None and ds.mask is None:
                self.mask = None
            else:
                if self.mask is None and ds.mask is not None:
                    self.mask = np.zeros(np.shape(self.data))
                elif self.mask is not None and ds.mask is None:
                    ds.mask = np.zeros(np.shape(ds.data))
                self.mask = np.hstack((self.mask,ds.mask))
            
            #Regenerate Tcenter?
            #Add extras together?



    def getData(self,remove_baseline=True):
        if remove_baseline:
            self.remove_baseline()
        return self.data

    def getACF(self,remove_baseline=True): 
        if self.acf is None:
            return self.acf2d(remove_baseline=remove_baseline)
        return self.acf


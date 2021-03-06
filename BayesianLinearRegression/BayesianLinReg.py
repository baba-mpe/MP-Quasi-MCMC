#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Oct  1 15:31:25 2018

@author: Tobias Schwedes

Script to implement Bayesian linear regression using importance sampling /
Rao-Blackwellisation for multiple proposal Quasi-MCMC with an independent 
proposal sampler that learns adaptively from past samples.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
from Data import DataGen
from Seed import SeedGen
#from Seed_digShift import SeedGen


class BayesianLinReg:
    
    def __init__(self, d, alpha, x0, N, StepSize, PowerOfTwo, \
                 InitMean, InitCov, Stream, WeightIn=0):
    
        """
        Implements the Bayesian Linear Regression based on Data set "Data.txt" 
        by using importance sampling / Rao-Blackwellisation for multiple 
        proposal Quasi-MCMC with an independent proposal sampler that learns 
        adaptively from past samples.
    
        Inputs:
        -------   
        d               - int 
                        dimension of posterior    
        alpha           - float
                        Standard deviation for Observation noise
        x0              - array_like
                        d-dimensional array; starting value
        N               - int 
                        number of proposals per iteration
        StepSize        - float 
                        step size for proposed jump in mean
        PowerOfTwo      - int
                        defines size S of seed by S=2**PowerOfTwo-1
        InitMean        - array_like 
                        d-dimensional initial proposal mean
        InitCov         - array_like
                        dxd-dimensional initial proposal covariance
        Stream          - string
                        either 'cud' or 'iid'; defining what seed is used
        WeightIn        - float
                        if BurnIn-run existed, weight initial esitmates
                        by int(WeightIn/N)-times                
        """
    
        #################
        # Generate Data #
        #################
        
        Data            = DataGen(alpha, d)
        X               = Data.getDesignMatrix()
        Obs             = Data.getObservations()
        NumOfSamples    = Data.getNumOfSamples()
        
        ##################################
        # Choose stream for Markoc Chain #
        ##################################
    
        xs = SeedGen(d+1, PowerOfTwo, Stream)
    
        ###########################################
        # Compute prior and likelihood quantities #
        ###########################################
        
        # Compute covariance of g-prior
        g = 1./NumOfSamples
        sigmaSq = 1./alpha
        G_prior = sigmaSq / g * np.linalg.inv(np.dot(X.T,X))
        InvG_prior = np.linalg.inv(G_prior)
           
         
        ##################
        # Initialisation #
        ##################
    
        # List of samples to be collected
        self.xVals = list()
        self.xVals.append(x0)
    
        # Iteration number
        NumOfIter = int(int((2**PowerOfTwo-1)/(d+1))*(d+1)/(N))
        print ('Total number of Iterations = ', NumOfIter)
    
        # set up acceptance rate array
        self.AcceptVals = list()
    
        # initialise
        xI = self.xVals[0]
        I = 0
        
        
        # Number of iterations used for initial approximated posterior mean
        M = int(WeightIn/N)+1        
        
        
        # Weighted Sum and Covariance Arrays
        self.WeightedSum = np.zeros((NumOfIter+M,d))
        self.WeightedCov = np.zeros((NumOfIter+M,d,d)) 
        self.WeightedFunSum = np.zeros((NumOfIter+M,d))
        self.WeightedSum[0:M,:] = InitMean
        self.WeightedCov[0:M,:] = InitCov 
        

        # Approximate Posterior Mean and Covariance as initial estimates
        self.ApprPostMean = InitMean
        self.ApprPostCov = InitCov        
        

        # Cholesky decomposition of initial Approximate Posterior Covariance
        CholApprPostCov = np.linalg.cholesky(self.ApprPostCov)
        InvApprPostCov = np.linalg.inv(self.ApprPostCov)
        
        
        ####################
        # Start Simulation #
        ####################
    
        for n in range(NumOfIter):
            
            ######################
            # Generate proposals #
            ######################
              
            # Load stream of points in [0,1]^d
            U = xs[n*(N):(n+1)*(N),:]
            
            # Sample new proposed States according to multivariate t-distribution               
            y = self.ApprPostMean + np.dot(norm.ppf(U[:,:d], loc=np.zeros(d), \
                                                    scale=StepSize), CholApprPostCov)
            
            # Add current state xI to proposals    
            Proposals = np.insert(y, 0, xI, axis=0)
    
    
            ########################################################
            # Compute probability ratios = weights of IS-estimator #
            ########################################################
    
            # Compute Log-posterior probabilities
            LogPriors = -0.5*np.dot(np.dot(Proposals, InvG_prior), Proposals.T).diagonal(0) # Zellner's g-prior
            fs = np.dot(X,Proposals.T)
            LogLikelihoods  = -0.5*alpha*np.dot(Obs-fs.T, (Obs-fs.T).T).diagonal(0)
            LogPosteriors   = LogPriors + LogLikelihoods
    
            # Compute Log of transition probabilities
            LogK_ni = -0.5*np.dot(np.dot(Proposals-self.ApprPostMean, InvApprPostCov/(StepSize**2)), \
                                 (Proposals - self.ApprPostMean).T).diagonal(0)
            LogKs = np.sum(LogK_ni) - LogK_ni # from any state to all others
            

            # Compute weights
            LogPstates = LogPosteriors + LogKs
            Sorted_LogPstates = np.sort(LogPstates)
            LogPstates = LogPstates - (Sorted_LogPstates[0] + \
                    np.log(1 + np.sum(np.exp(Sorted_LogPstates[1:] - Sorted_LogPstates[0]))))
            Pstates = np.exp(LogPstates)
    
    
            #######################
            # Compute IS-estimate #
            #######################
    
            # Compute weighted sum as posterior mean estimate
            WeightedStates = np.tile(Pstates, (d,1)) * Proposals.T
            self.WeightedSum[n+M,:] = np.sum(WeightedStates, axis=1).copy()

            # Update Approximate Posterior Mean
            self.ApprPostMean = np.mean(self.WeightedSum[:n+M+1,:], axis=0) 

            # Compute weighted sum as posterior covariance estimate
            B1 = (Proposals - self.ApprPostMean).reshape(N+1,d,1) 
            B2 = np.transpose(B1,(0,2,1)) 
            A = np.matmul(B1, B2)
            self.WeightedCov[n+M,:,:] = np.sum((np.tile(Pstates, (d,d,1)) * A.T).T, axis=0)

            InvApprPostCov = np.linalg.inv(self.ApprPostCov)

            if n> 2*d/N: # makes sure NumOfSamples > d for covariance estimate
                self.ApprPostCov = np.mean(self.WeightedCov[:n+M+1,:,:], axis=0)
                CholApprPostCov = np.linalg.cholesky(self.ApprPostCov)
                InvApprPostCov = np.linalg.inv(self.ApprPostCov)
    
            ##################################
            # Sample according to IS-weights #
            ##################################
    
            # Sample N new states 
            PstatesSum = np.cumsum(Pstates)
            Is = np.searchsorted(PstatesSum, U[:,d:].flatten())
            xvals_new = Proposals[Is]
            self.xVals.append(xvals_new)
    
            # Compute approximate acceptance rate
            AcceptValsNew = 1. - Pstates[Is]
            self.AcceptVals.append(AcceptValsNew)
    
            # Update current state
            I = Is[-1]
            xI = Proposals[I,:]
    
    
    def getSamples(self, BurnIn=0):
        
        """
        Compute samples from posterior from MP-QMCMC
        
        Inputs:
        ------
        BurnIn  - int 
                Burn-In period
        
        Outputs:
        -------
        Samples - array_like
                (Number of samples) x d-dimensional arrayof Samples      
        """
        
        Samples = np.concatenate(self.xVals[1:], axis=0)[BurnIn:,:]
                
        return Samples
       
        
    def getAcceptRate(self, BurnIn=0):
        
        """
        Compute acceptance rate of MP-QMCMC
        
        Inputs:
        ------
        BurnIn  - int
                Burn-In period
        
        Outputs:
        -------
        AcceptRate - float
                    average acceptance rate of MP-QMCMC 
        """    
        
        AcceptVals = np.concatenate(self.AcceptVals)[BurnIn:]
        AcceptRate = np.mean(AcceptVals)
        
        return AcceptRate

     
    def getIS_MeanEstimate(self, N, BurnIn=0):
        
        """
        Compute importance sampling estimate

        Inputs:
        -------   
        N               - int 
                        number of proposals per iteration      
        BurnIn          - int
                        Burn-In period  
    
        Outputs:
        -------
        WeightedMean    - array_like
                        d-dimensional array
        """            
        
        WeightedMean = np.mean(self.WeightedSum[int(BurnIn/N):,:], axis=0)
        
        return WeightedMean
    

    def getIS_FunMeanEstimate(self, N, BurnIn=0):
        
        """
        Compute importance sampling estimate

        Inputs:
        -------   
        N               - int 
                        number of proposals per iteration      
        BurnIn          - int
                        Burn-In period  
                
        Outputs:
        -------
        WeightedMean    - array_like
                        d-dimensional array
        """            
        
        WeightedMean = np.mean(self.WeightedFunSum[int(BurnIn/N):,:], axis=0)
        
        return WeightedMean    
  

    def getIS_CovEstimate(self, N, BurnIn=0):
        
        """
        Compute importance sampling covariance estimate

        Inputs:
        -------   
        N               - int 
                        number of proposals per iteration      
        BurnIn          - int
                        Burn-In period  
        
        Outputs:
        -------
        WeightedCov - d-dimensional array
        """            
        
        WeightedCov = np.mean(self.WeightedCov[int(BurnIn/N):,:,:], axis=0)
        
        return WeightedCov    
    
      
    def getMarginalHistogram(self, Index=0, BarNum=100, BurnIn=0):
        
        """
        Plot histogram of marginal distribution for posterior samples using 
        MP-QMCMC
        
        Inputs:
        ------
        Index   - int
                index of dimension for marginal distribution
        BurnIn  - int
                Burn-In period
        
        Outputs:
        -------
        Plot
        """         

        Fig = plt.figure()
        SubPlot = Fig.add_subplot(111)
        SubPlot.hist(self.getSamples(BurnIn)[:,Index], BarNum, label = "PDF Histogram", density = True)
        
        return Fig



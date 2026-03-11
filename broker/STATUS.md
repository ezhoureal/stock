Manual Steps Required (for Live Paper Trading with Futu)                                                        
                                                                                                                  
  To use real paper trading with Futu OpenAPI, you need to:                                                       
                                                                                                                  
  1. Install Futu OpenD                                                                                           
    - Download from: https://www.futunn.com/download/OpenD                                                        
    - Run OpenD gateway on your machine                                                                           
  2. Create Futu Account                                                                                          
    - Register at Futu Securities (moomoo)                                                                        
    - Enable OpenAPI access in account settings                                                                   
  3. Configure Connection                                                                                         
    - The .env file is already configured with defaults:                                                          
    BROKER_TYPE=futu                                                                                              
  FUTU_HOST=127.0.0.1                                                                                             
  FUTU_PORT=11111                                                                                                 
  PAPER_TRADING=true                                                                                              
  4. Start OpenD before running live trading                                                                      
                                                                                                                  
  ---                                                                                                             
  Current Limitations                                                                                             
                                                                                                                  
  1. No Futu broker implementation - The code references Futu but only mock broker is implemented                 
  2. Order cancellation has a minor bug (test shows "Failed to cancel order" for limit orders below market)       
                                                         
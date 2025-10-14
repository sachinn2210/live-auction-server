
#include "AuctionServer.h"
#include<iostream>
#include<signal.h>

AuctionServer* serverInstance=nullptr;

void signalHandler(int number)
{
    cout<<"\n Interrupt signal ("<<number<<") received.Shutting down server..."<<endl;

    if(serverInstance)
    {
       serverInstance->stopServer();
    }
    exit(number);
}

int main()
{
    signal(SIGINT,signalHandler);

    AuctionServer server;
    serverInstance=&server;

    try
    {
        server.startServer();
    }
    catch(const std::exception& e)
    {
       cerr<<"Exception caught in main:"<<e.what()<<endl;
       return 1;
    }
    catch(...)
    {
       cerr<<"Unknown exception."<<endl;
       return 1;
    }
    return 0;
}

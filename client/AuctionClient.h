
#pragma once

#include<iostream>
#include<string>
#include<thread>
#include<mutex>

#include<winsock2.h>
#include<ws2tcpip.h>

using namespace std;

#define PORT "8000"
#define SERVER_IP "127.0.0.1"

class AuctionClient
{
    private:
       SOCKET client_socket=INVALID_SOCKET;
       thread receive_thread;
       bool is_connected=false;

    public:
       bool initializeWinsock();
       void cleanupWinsock();
       bool connecttoserver();
       void receivemessages();

       AuctionClient();
       ~AuctionClient();
       void startClient();
       void stopClient();
       void sendBid(string& bid_amount);
};
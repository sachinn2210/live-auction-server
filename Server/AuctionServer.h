//this header file contains AuctionServer class.

#pragma once //this preprocessor directive ensures that file is included only once while we compile.

// Windows-specific defines (must come before winsock2.h)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

// Standard C++ headers first
#include <iostream>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <thread>
#include <mutex>
#include <sstream>

// Windows socket headers (must come after standard headers)
#include <winsock2.h>  // this library is for socket programming
#include <ws2tcpip.h>  // this library provides getaddrinfo functions

using namespace std;

//Defining constants here .
#define PORT "8000"
#define MAX_CLIENTS 10

//represents a particular item on which auction is going to be held
class AuctionItem
{
public:
    string itemname;//stores the item name 
    double currentBid;
    SOCKET currentBiddersocketID;

    AuctionItem()
    {
        this->itemname="Default Auction Item";
        this->currentBid=0.0;
        this->currentBiddersocketID=INVALID_SOCKET;
    }
};

struct ClientInfo{
    SOCKET socket;
    string username;
    string auction_code;
};

class AuctionServer
{
    AuctionItem current_item;
    std::mutex clients_mutex;
    std::mutex auction_mutex;
    vector<SOCKET>client_sockets;

    map<string,vector<ClientInfo>>auction_rooms;
    SOCKET listen_socket=INVALID_SOCKET;
    SOCKET monitor_socket=INVALID_SOCKET;  

    bool initializewinsock();
    void cleanupwinsock();
    void setupListenSocket();
    void manageclient(SOCKET client_socket);
    void broadcastMessage(string& message,SOCKET avoid_socket=INVALID_SOCKET);

    void addClientToRoom(ClientInfo client);
    void removeClient(ClientInfo client);
    void broadcastToRoom(const string &auction_code, const string &message);
    void broadcastToMonitor(const string &message);  
    void removeSocketFromList(SOCKET client_socket); 
    vector<string> split(string &s,char delimiter);

public:
    AuctionServer();
    ~AuctionServer();
    void startServer();
    void stopServer();
};
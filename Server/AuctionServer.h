//this header file contains AuctionServer class.

#pragma once //this preprocessor directive ensures that file is included only once while we compile.
#include<iostream>
#include<vector>
#include<thread>
#include<mutex>
#include<string>
//Including Libraries for socket 
#include<winsock2.h>//this library is for socket programming
#include<ws2tcpip.h>//this library provides getaddrinfo functions
#include<map>//for auction room mapping
#include<algorithm>
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
    mutex clients_mutex;
    mutex auction_mutex;
    vector<SOCKET>client_sockets;

    map<string,vector<ClientInfo>>auction_rooms;
    SOCKET listen_socket=INVALID_SOCKET;
    SOCKET monitor_socket=INVALID_SOCKET;  // ADDED: Monitor socket declaration

    bool initializewinsock();
    void cleanupwinsock();
    void setupListenSocket();
    void manageclient(SOCKET client_socket);
    void broadcastMessage(string& message,SOCKET avoid_socket=INVALID_SOCKET);

    void addClientToRoom(ClientInfo client);
    void removeClient(ClientInfo client);
    void broadcastToRoom(const string &auction_code, const string &message);
    void broadcastToMonitor(const string &message);  // ADDED: Declaration
    void removeSocketFromList(SOCKET client_socket);  // ADDED: New helper function
    vector<string> split(string &s,char delimiter);

public:
    AuctionServer();
    ~AuctionServer();
    void startServer();
    void stopServer();
};
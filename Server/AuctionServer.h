
//this header file contains AuctionServer class.

#pragma once //this preprocessor directive ensures that file is included only once while we compile.

#include<iostream>
#include<vector>
#include<thread>
#include<mutex>
#include<string>

//Including Libraries for socket 
#include<winsock2.h>//this library is for socket programming
#include<ws2tcpip.h>//this library provides getaddringo gunctions
using namespace std;

//Defining constants here .
#define PORT "8000"
#define MAX_CLIENTS 10

//representa a particular item on which auction is going to be held
class AuctionItem
{
public:

string itemname;//stores the item on 
double currentBid;
int currentBiddersocketID;

AuctionItem()
{
    this->itemname="Default Auction Item";
    this->currentBid=0.0;
    this->currentBiddersocketID=INVALID_SOCKET;
}
};

class AuctionServer
{
  AuctionItem current_item;
  mutex clients_mutex;
  mutex auction_mutex;
  vector<SOCKET>client_sockets;

  SOCKET listen_socket=INVALID_SOCKET;

  bool initializewinsock();
  void cleanupwinsock();
  void setupListenSocket();
  void manageclient(SOCKET client_socket);
  void broadcastMessage(string& message,SOCKET avoid_socket=INVALID_SOCKET);

public:
     AuctionServer();
     ~AuctionServer();
     void startServer();
     void stopServer();
};
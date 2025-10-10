#include "AuctionServer.h"

//constructor
AuctionServer::AuctionServer()
{
    cout<<"Starting auction server"<<endl;
    if(!initializewinsock())
    {
        exit(EXIT_FAILURE);
    }
}

//destructor
AuctionServer::~AuctionServer()
{
stopServer();
cleanupwinsock();
cout<<"Auction server shut down successfully."<<endl;
}

//initliaze the windows socket
bool AuctionServer::initializewinsock()
{
    WSADATA wsaData;

    int status=WSAStartup(MAKEWORD(2,2),&wsaData);

    if(status!=0)
    {
        cout<<"WSAStartup failed with error: "<<status<<endl;
        return false;
    }

    cout<<"Winsock initialized successfully."<<endl;
    return true;
}

//clean up socket resources to avoid memory leaks
void AuctionServer::cleanupwinsock()
{
    //close the listening socket
    if(listen_socket!=INVALID_SOCKET)
    {
        closesocket(listen_socket);
        listen_socket=INVALID_SOCKET;
    }
    //Terminate winsock
    WSACleanup();
}

//create,bind and set server socket to listen mode
//this function will accept both IPv4 and IPv6 adddresses.
void AuctionServer::setupListenSocket()
{
    struct addrinfo * result=NULL,hints;//comes from wsc2pip.h. modern version of normal socket programming

    int errorcheck;

    ZeroMemory(&hints,sizeof(hints));//initialize sturcture to zero

    hints.ai_family=AF_UNSPEC;//accept both IPV4 and IPV6 address
    //AF_INET:IPv4 ,AF_INET6:IPv6 
    hints.ai_socktype=SOCK_STREAM;//streaming socket
    hints.ai_protocol=IPPROTO_TCP;//tcp protocol
    hints.ai_flags=AI_PASSIVE;//server socker used to listen clients

    //step 1:deduce server address and port
    errorcheck=getaddrinfo(nullptr,PORT,&hints,&result);
    if(errorcheck !=0 )
    {
        cout<<"geraddrinfo failed with error: "<<errorcheck<<endl;
        cleanupwinsock();
        exit(EXIT_FAILURE);
    }

    //step 2:create listening socket
    listen_socket=socket(result->ai_family,result->ai_socktype,result->ai_protocol);
    if(listen_socket==INVALID_SOCKET)
    {
       cerr<<"Error at socket:"<<WSAGetLastError()<<endl;
       freeaddrinfo(result);
       cleanupwinsock();
       exit(EXIT_FAILURE);
    }

    //Step 3:bind socket to lcoal address and port
    errorcheck=bind(listen_socket,result->ai_addr,(int)result->ai_addrlen);
    if(errorcheck==SOCKET_ERROR)
    {
      cerr<<"Bind failed with error:"<<WSAGetLastError()<<endl;
      freeaddrinfo(result);
       cleanupwinsock();
       exit(EXIT_FAILURE);
    }

     freeaddrinfo(result);

     //step 4:Set socket to listening mode
     errorcheck=listen(listen_socket,MAX_CLIENTS);

     if(errorcheck==SOCKET_ERROR)
     {
         cerr<<"Listen failed with error:"<<WSAGetLastError()<<endl;
       cleanupwinsock();
       exit(EXIT_FAILURE);
     }

     cout<<"Server socket listening on port"<<PORT<<"..\n";

}
//start the server
void AuctionServer::startServer()
{
    setupListenSocket();
    cout<<"Waiting for client to connect.."<<endl;

    SOCKET client_socket=INVALID_SOCKET;

    while(true)
    {
        //accept new connection
        client_socket=accept(listen_socket,NULL,NULL);

        if(client_socket==INVALID_SOCKET)
        {
            if(WSAGetLastError()==WSAEINTR)
            {
                break;//exit loop if interrupt occured
            }
            cerr<<"Accept failed with error:"<<WSAGetLastError()<<endl;
            continue;
        }
    

    //add client socket to list.
    //locking clients vector
    {
    lock_guard<mutex>lock(clients_mutex);
    client_sockets.push_back(client_socket);
    cout<<"Client connected.Total clients: "<<client_sockets.size()<<endl;
    }
    //start new thread for connected client
    thread client_thread(&AuctionServer::manageclient,this,client_socket);
    client_thread.detach();//run the thread independently.
    }
}


void AuctionServer::manageclient(SOCKET client_socket)
{
    char buffer[512];
    int status;
    int client_id=client_socket;//identify client

    string message="Welcome ! Current item: "+current_item.itemname+",Current Bid: "+ to_string(current_item.currentBid)+"\n";

    send(client_socket,message.c_str(),(int) message.length(),0);

    do
    {
      status=recv(client_socket,buffer,512,0);

      if(status>0)
      {
        buffer[status]='\0';
        string received_message(buffer);
        cout<<"Received bid from client"<<client_id<<": "<<received_message<<endl;


        try
        {
           //bid amount
           double new_bid=stod(received_message);

           //lock auction data 
           lock_guard<mutex>lock(auction_mutex);

           if(new_bid>current_item.currentBid)
           {
            current_item.currentBid=new_bid;
            current_item.currentBiddersocketID=client_socket;

            string success_message="NEW HIGH BID! "+to_string(new_bid) + "by Client "+to_string(client_id) +"\n";
            broadcastMessage(success_message,INVALID_SOCKET);
           }
           else
           {
            string lower_message="Bid"+to_string(new_bid)+" is too low.Current high bid is "+ to_string(current_item.currentBid)+"\n";
            send(client_socket,lower_message.c_str(),(int)lower_message.length(),0);
           }
        }
        catch(const std::invalid_argument& e)
        {
            string error_message="Invalid input.Please enter numerical bid.\n";
            send(client_socket,error_message.c_str(),(int)error_message.length(),0);
        }
        
      }
      else if(status==0)
      {
        cout<<"Connection is closed from client "<<client_id<<endl;
      }
      else
      {
        cerr<<" Recv failed with error: "<<WSAGetLastError()<<endl;
      }
    }while(status>0);

    //critical section:remove socket from list
    {
        lock_guard<mutex>lock(clients_mutex);

        for(auto it=client_sockets.begin();it!=client_sockets.end();it++)
        {
            if(*it ==client_socket)
            {
                client_sockets.erase(it);
                break;
            }
        }
        cout<<"Client disconnected. Total clients: "<<client_sockets.size()<<endl;
    }
   closesocket(client_socket);
}

void AuctionServer::broadcastMessage(string& message,SOCKET avoid_socket)
{
    //lock vector 
    lock_guard<mutex>lock(clients_mutex);

    for(SOCKET client_sock:client_sockets)
    {
        if(client_sock!=INVALID_SOCKET && client_sock !=avoid_socket)
        {
            int isSend=send(client_sock,message.c_str(),(int)message.length(),0);

            if(isSend==SOCKET_ERROR)
            {
                cerr<<"Send failed to socket "<<client_sock<<"with error :" <<WSAGetLastError()<<endl;
            }
        }
    }
}

void AuctionServer::stopServer()
{
    //close all active client connections
    {
    lock_guard<mutex>lock(clients_mutex);

    for(SOCKET client_socket:client_sockets)
    {
        shutdown(client_socket,SD_SEND);
        closesocket(client_socket);
    }
    client_sockets.clear();
   }
    
   //close listening socket
   if(listen_socket !=INVALID_SOCKET)
   {
    closesocket(listen_socket);
    listen_socket=INVALID_SOCKET;
   }
}
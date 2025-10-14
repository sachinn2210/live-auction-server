
#include "AuctionClient.h"//including the header file

//constructor
AuctionClient::AuctionClient()
{
    cout<<"Initializing auction client"<<endl;
    if(!initializeWinsock())
    {
        exit(EXIT_FAILURE);
    }
}

//destructor
AuctionClient::~AuctionClient()
{
    stopClient();
    cleanupWinsock();
    cout<<"Auction client shut down."<<endl;
}

//initliaze winsock
bool AuctionClient::initializeWinsock()
{
    WSAData wsaData;
    int status=WSAStartup(MAKEWORD(2,2),&wsaData);
    if(status!=0)
    {
        cout<<"WSAStartup failed with error: "<<status<<endl;
        return false;
    }
    return true;
}

//cleanup the resources acquired by winsock
void AuctionClient::cleanupWinsock()
{
    if(client_socket!=INVALID_SOCKET)
    {
        closesocket(client_socket);
        client_socket=INVALID_SOCKET;
    }
    WSACleanup();
}

//this function handles connection to server
bool AuctionClient::connecttoserver()
{
    struct addrinfo  *result=NULL,*ptr=NULL,hints;

    ZeroMemory(&hints,sizeof(hints));

    hints.ai_family=AF_UNSPEC;
    hints.ai_socktype=SOCK_STREAM;
    hints.ai_protocol=IPPROTO_TCP;

    //resolve server address and port
    int errorcheck=getaddrinfo(SERVER_IP,PORT,&hints,&result);
    if(errorcheck !=0)
    {
        cerr<<"getaddrinfo failed with error:"<<errorcheck<<endl;
        return false;
    }

    //connect to an address
    for(ptr=result;ptr!=NULL;ptr=ptr->ai_next)
    {
        client_socket=socket(ptr->ai_family,ptr->ai_socktype,ptr->ai_protocol);

        if(client_socket==INVALID_SOCKET)
        {
            cerr<<"Error at socket :"<<WSAGetLastError()<<endl;
            continue;
        }
    

    //connect to server
    errorcheck=connect(client_socket,ptr->ai_addr,(int)ptr->ai_addrlen);
    if(errorcheck==SOCKET_ERROR)
    {
        closesocket(client_socket);
        client_socket=INVALID_SOCKET;
        continue;
    }
    break;
     }
freeaddrinfo(result);
if(client_socket==INVALID_SOCKET)
{
    cerr<<"Unable to connect to server!"<<endl;
    return false;
}
is_connected=true;
cout<<"Successfully connected to auction server."<<endl;
return true;
}

//this is a function which continuously receive messages from server
void AuctionClient::receivemessages()
{
    char buffer[512];
    int status;

    do
    {
       status=recv(client_socket,buffer,512,0);

       if(status>0)
       {
        buffer[status]='\0';
        cout<<"\n[SERVER] "<<buffer<<"\n> "<<flush;
       }
       else if(status==0)
       {
        //status will be 0 when connection is closed by server
        cout<<"\n connection closed by server."<<endl;
        is_connected=false;
       }
       else
       {
        //handle errors
        if(WSAGetLastError() != WSAECONNRESET)
        {
            cerr<<"\n receive failed with error: "<<WSAGetLastError()<<endl;
        }
        is_connected=false;
       }
    } while (status>0 && is_connected);
    client_socket=INVALID_SOCKET;
}

//establishing client connection
void AuctionClient::startClient()
{
    if(!connecttoserver())
    {
        return;
    }

    //start receiving thread
    receive_thread=thread(&AuctionClient::receivemessages,this);
    receive_thread.detach();

    string bid_input;
    cout<<"Enter your bid amount (or 'quit' to exit):\n";

    //loop used to send bids
    while(is_connected)
    {
        getline(cin,bid_input);

       if(bid_input=="quit")
       {
        break;
       }

       sendBid(bid_input);
       cout<<"> "<<flush;
    }
}

//this function sends bid amount to server
void AuctionClient::sendBid(string &bid_amount)
{
    if(!is_connected || client_socket==INVALID_SOCKET)
    {
        cerr<<"cannot send bid amount to server.Not connected to server."<<endl;
        return;
    }

    int result=send(client_socket,bid_amount.c_str(),(int)bid_amount.length(),0);
    if(result==SOCKET_ERROR)
    {
        cerr<<"Error send failed with error:"<<WSAGetLastError()<<endl;
    }
}

//stop client and join threads
void AuctionClient::stopClient()
{
    is_connected=false;

    //closing the connection
    if(client_socket!=INVALID_SOCKET)
    {
        shutdown(client_socket,SD_BOTH);
        closesocket(client_socket);
        client_socket=INVALID_SOCKET;
    }

    //join the receive thread
    if(receive_thread.joinable())
    {
        receive_thread.join();
    }
}

#include "AuctionClient.h"

int main()
{
    AuctionClient client;

    try
    {
        client.startClient();
    }
    catch(const std::exception& e)
    {
        cerr<<"Exception at client side:"<<e.what()<<endl;
        return 1;
    }
    return 0;
}
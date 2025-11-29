#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include "AuctionServer.h"
#include <sstream>
#include <algorithm>

// Constructor
AuctionServer::AuctionServer() {
    cout << "Starting auction server" << endl;
    if (!initializewinsock()) {
        exit(EXIT_FAILURE);
    }
}

// Destructor
AuctionServer::~AuctionServer() {
    stopServer();
    cleanupwinsock();
    cout << "Auction server shut down successfully." << endl;
}

// Initialize WinSock
bool AuctionServer::initializewinsock() {
    WSADATA wsaData;
    int status = WSAStartup(MAKEWORD(2, 2), &wsaData);

    if (status != 0) {
        cerr << "WSAStartup failed with error: " << status << endl;
        return false;
    }

    cout << "Winsock initialized successfully." << endl;
    return true;
}

// Cleanup WinSock
void AuctionServer::cleanupwinsock() {
    if (listen_socket != INVALID_SOCKET) {
        closesocket(listen_socket);
        listen_socket = INVALID_SOCKET;
    }
    WSACleanup();
}

// Create/bind/listen socket
void AuctionServer::setupListenSocket() {
    struct addrinfo *result = NULL, hints;
    int errorcheck;

    ZeroMemory(&hints, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    hints.ai_flags = AI_PASSIVE;

    errorcheck = getaddrinfo(nullptr, PORT, &hints, &result);
    if (errorcheck != 0) {
        cerr << "getaddrinfo failed with error: " << errorcheck << endl;
        cleanupwinsock();
        exit(EXIT_FAILURE);
    }

    listen_socket = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (listen_socket == INVALID_SOCKET) {
        cerr << "Error at socket: " << WSAGetLastError() << endl;
        freeaddrinfo(result);
        cleanupwinsock();
        exit(EXIT_FAILURE);
    }

    if (result->ai_family == AF_INET6) {
        int ipv6only = 0;
        if (setsockopt(listen_socket, IPPROTO_IPV6, IPV6_V6ONLY,
                       (char *)&ipv6only, sizeof(ipv6only)) == SOCKET_ERROR) {
            cerr << "Warning: Could not set dual-stack mode: " << WSAGetLastError() << endl;
        } else {
            cout << "Dual-stack mode enabled - accepting both IPv4 and IPv6 connections" << endl;
        }
    }

    errorcheck = bind(listen_socket, result->ai_addr, (int)result->ai_addrlen);
    if (errorcheck == SOCKET_ERROR) {
        cerr << "Bind failed with error: " << WSAGetLastError() << endl;
        freeaddrinfo(result);
        cleanupwinsock();
        exit(EXIT_FAILURE);
    }

    freeaddrinfo(result);
    errorcheck = listen(listen_socket, MAX_CLIENTS);
    if (errorcheck == SOCKET_ERROR) {
        cerr << "Listen failed with error: " << WSAGetLastError() << endl;
        cleanupwinsock();
        exit(EXIT_FAILURE);
    }

    cout << "Server socket listening on port " << PORT << "..." << endl;
}

// Start the server main loop
void AuctionServer::startServer() {
    setupListenSocket();
    cout << "Waiting for clients to connect..." << endl;

    SOCKET client_socket = INVALID_SOCKET;

    while (true) {
        client_socket = accept(listen_socket, NULL, NULL);
        if (client_socket == INVALID_SOCKET) {
            if (WSAGetLastError() == WSAEINTR) break;
            cerr << "Accept failed with error: " << WSAGetLastError() << endl;
            continue;
        }

        {
            std::lock_guard<std::mutex> lock(clients_mutex);
            client_sockets.push_back(client_socket);
            cout << "Client connected. Total clients: " << client_sockets.size() << endl;
        }

        std::thread client_thread(&AuctionServer::manageclient, this, client_socket);
        client_thread.detach();
    }
}

// Manage a connected client
void AuctionServer::manageclient(SOCKET client_socket) {
    char buffer[512];
    int status;
    ClientInfo client;
    client.socket = client_socket;
    bool is_monitor = false;

    string welcome = "Welcome to the Auction Server!\n";
    send(client_socket, welcome.c_str(), (int)welcome.length(), 0);

    while (true) {
        status = recv(client_socket, buffer, 512, 0);
        if (status <= 0) {
            cout << "[DISCONNECT] Client disconnected.\n";
            if (!is_monitor) {
                removeClient(client);
                removeSocketFromList(client_socket);
            } else {
                std::lock_guard<std::mutex> lock(clients_mutex);
                if (monitor_socket == client_socket) {
                    monitor_socket = INVALID_SOCKET;
                }
                shutdown(client_socket, SD_BOTH);
                closesocket(client_socket);
                cout << "[MONITOR] Monitor client disconnected\n";
            }
            break;
        }

        buffer[status] = '\0';
        string msg(buffer);
        msg.erase(remove(msg.begin(), msg.end(), '\n'), msg.end());
        msg.erase(remove(msg.begin(), msg.end(), '\r'), msg.end());

        cout << "[RECV] " << msg << endl;

        if (msg == "MONITOR_CLIENT") {
            is_monitor = true;
            std::lock_guard<std::mutex> lock(clients_mutex);

            if (monitor_socket != INVALID_SOCKET) {
                cout << "[MONITOR] Replacing existing monitor client\n";
                shutdown(monitor_socket, SD_BOTH);
                closesocket(monitor_socket);
            }

            monitor_socket = client_socket;
            cout << "[MONITOR] Monitor client registered\n";
            string ack = "Monitor mode activated. You will receive all auction updates.\n";
            send(client_socket, ack.c_str(), (int)ack.length(), 0);
            continue;
        }

        if (is_monitor) continue;

        if (msg == "LEAVE") {
            broadcastToRoom(client.auction_code, client.username + " left the auction.\n");
            removeClient(client);
            removeSocketFromList(client_socket);
            break;
        }

        vector<string> parts = split(msg, '|');
        if (parts.size() == 3 && parts[2] == "JOIN") {
            client.username = parts[0];
            client.auction_code = parts[1];
            addClientToRoom(client);

            string join_msg = "[JOIN] " + client.username + " joined " + client.auction_code + "\n";
            broadcastToRoom(client.auction_code, join_msg);
            broadcastToMonitor(join_msg);
        }
        else if (parts.size() == 3) {
            string username = parts[0];
            string auction_code = parts[1];
            string bid_value = parts[2];

            try {
                double bid = stod(bid_value);
                string message = "NEW HIGH BID! " + to_string(bid) + " by " + username + " in " + auction_code + "\n";
                broadcastToRoom(auction_code, message);
                broadcastToMonitor(message);
                cout << "[BID] " << username << " placed " << bid << " on " << auction_code << endl;
            }
            catch (...) {
                string err = "Invalid bid input.\n";
                send(client_socket, err.c_str(), (int)err.length(), 0);
            }
        }
        else {
            string err = "Unrecognized message format.\n";
            send(client_socket, err.c_str(), (int)err.length(), 0);
        }
    }
}

void AuctionServer::broadcastMessage(string &message, SOCKET avoid_socket) {
    std::lock_guard<std::mutex> lock(clients_mutex);
    for (SOCKET client_sock : client_sockets) {
        if (client_sock != INVALID_SOCKET && client_sock != avoid_socket) {
            int sent = send(client_sock, message.c_str(), (int)message.length(), 0);
            if (sent == SOCKET_ERROR) {
                cerr << "Send failed to socket " << client_sock
                     << " with error: " << WSAGetLastError() << endl;
            }
        }
    }
}

void AuctionServer::broadcastToMonitor(const string &message) {
    std::lock_guard<std::mutex> lock(clients_mutex);
    if (monitor_socket != INVALID_SOCKET) {
        int sent = send(monitor_socket, message.c_str(), (int)message.length(), 0);
        if (sent == SOCKET_ERROR) {
            cerr << "[MONITOR] Send failed with error: " << WSAGetLastError() << endl;
            shutdown(monitor_socket, SD_BOTH);
            closesocket(monitor_socket);
            monitor_socket = INVALID_SOCKET;
        }
    }
}

void AuctionServer::stopServer() {
    std::lock_guard<std::mutex> lock(clients_mutex);

    for (SOCKET client_socket : client_sockets) {
        shutdown(client_socket, SD_BOTH);
        closesocket(client_socket);
    }
    client_sockets.clear();

    if (monitor_socket != INVALID_SOCKET) {
        shutdown(monitor_socket, SD_BOTH);
        closesocket(monitor_socket);
        monitor_socket = INVALID_SOCKET;
    }

    if (listen_socket != INVALID_SOCKET) {
        closesocket(listen_socket);
        listen_socket = INVALID_SOCKET;
    }
}

vector<string> AuctionServer::split(string &s, char delimiter) {
    vector<string> tokens;
    string token;
    istringstream tokenStream(s);
    while (getline(tokenStream, token, delimiter)) {
        tokens.push_back(token);
    }
    return tokens;
}

void AuctionServer::addClientToRoom(ClientInfo client) {
    std::lock_guard<std::mutex> lock(clients_mutex);
    auction_rooms[client.auction_code].push_back(client);
    cout << "[INFO] " << client.username << " joined auction " << client.auction_code << endl;
}

void AuctionServer::removeClient(ClientInfo client) {
    std::lock_guard<std::mutex> lock(clients_mutex);
    auto &room = auction_rooms[client.auction_code];
    room.erase(remove_if(room.begin(), room.end(),
                         [&](const ClientInfo &c) { return c.socket == client.socket; }),
               room.end());
    closesocket(client.socket);

    if (room.empty()) {
        auction_rooms.erase(client.auction_code);
        cout << "[INFO] Auction room " << client.auction_code << " closed (empty)" << endl;
    }

    cout << "[INFO] " << client.username << " left auction " << client.auction_code << endl;
}

void AuctionServer::removeSocketFromList(SOCKET client_socket) {
    std::lock_guard<std::mutex> lock(clients_mutex);
    client_sockets.erase(remove(client_sockets.begin(), client_sockets.end(), client_socket),
                         client_sockets.end());
    shutdown(client_socket, SD_BOTH);
    closesocket(client_socket);
    cout << "[INFO] Socket removed from client list. Total clients: "
         << client_sockets.size() << endl;
}

void AuctionServer::broadcastToRoom(const string &auction_code, const string &message) {
    std::lock_guard<std::mutex> lock(clients_mutex);
    auto &room = auction_rooms[auction_code];
    for (auto &client : room) {
        send(client.socket, message.c_str(), (int)message.length(), 0);
    }
}

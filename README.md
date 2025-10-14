#  Multithreaded TCP Based Live Auction Server (C++)

This repository contains a **multithreaded TCP-based Live Auction Server and Client** built entirely in **C++** using socket programming. Multiple clients can connect simultaneously to participate in a **real-time auction** over TCP.

---

##  Features

-  TCP socket communication
-  Supports up to 10 concurrent clients
-  Multithreaded server using `std::thread`
-  Thread safety using `std::mutex`
-  Real-time bidding system
-  Windows compatible (uses Winsock2)

---

##  Requirements

Make sure the following are installed:

| Requirement | Version |
|-------------|----------|
| g++ compiler | **10 or higher** |
| Git | Latest |
| Windows OS |  Supported |
| Visual Studio Code (optional) | Recommended |

>  Ensure that your **g++ version is 10 or higher**, as this project uses modern **C++17 features and multithreading** (`<thread>`, `<mutex>`).

---

##  Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/Pavankumar-Batchu1185/Multithreaded-TCP-Based-Live-Auction-Server-
cd Multithreaded-TCP-Based-Live-Auction-Server-
```

### 2. Build the Server
```bash
cd server
g++ -std=c++17 AuctionServer.cpp main.cpp -o AuctionServer.exe -lws2_32
```

### 3.Build the Client
```bash
cd ../client
g++ -std=c++17 AuctionClient.cpp main.cpp -o AuctionClient.exe -lws2_32
```

## Run the application
### 1.Start the server
```bash
cd server
./AuctionServer.exe
```

### 2.Start a Client

Open a new terminal:
```bash
cd client
./AuctionClient.exe
```
You can open up to 10 client windows to simulate multiple bidders.

## Project Structure
```css
.
├── server
│   ├── AuctionServer.cpp
│   ├── main.cpp
├── client
│   ├── AuctionClient.cpp
│   ├── main.cpp
└── README.md
```


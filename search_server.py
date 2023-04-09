"""
Copyright 2019, University of Freiburg,
Chair of Algorithms and Data Structures.
Hannah Bast <bast@cs.uni-freiburg.de>
Patrick Brosi <brosi@cs.uni-freiburg.de>
Natalie Prange <prange@cs.uni-freiburg.de>
"""
import multiprocessing
import socket
import sys
import re
import time
from pathlib import Path
from urllib.parse import unquote
import qgram_index


class SearchServer:
    """
    A HTTP search server using a q gram index.

    No pre-defined tests are required this time. However, if you add new
    non-trivial methods, you should of course write tests for them.

    Your server should behave like explained in the lecture. For a given
    URL of the form http://<host>:<port>/search.html?q=<query>, your server
    should return a (static) HTML page that displays (1) an input field and a
    search button as shown in the lecture, (2) the query without any URL
    encoding characters and (3) the top-5 entities returned by your q-gram
    index (from exercise sheet 5) for the query.

    In the following, you will find some example URLs, each given with the
    expected query (%QUERY%) and the expected entities (%RESULT%, each in the
    format "<name>;<score>;<description>") that should be displayed by the
    HTML page returned by your server when calling the URL. Note that, as
    usual, the contents of the test cases is important, but not the exact
    syntax. In particular, there is no HTML markup given, as the layout of
    the HTML pages and the presentation of the entities is up to you. Please
    make sure that the HTML page displays at least the given query and the
    names, scores and descriptions of the given entities in the given order
    (descending sorted by scores).

     URL:
      http://<host>:<port>/search.html?q=angel
     RESPONSE:
      %QUERY%:
        angel
      %RESULT%:
       ["Angela Merkel;205;chancellor of Germany from 2005 to 2021",
        "Angelina Jolie;158;American actress (born 1975)",
        "angel;140;supernatural being or spirit in certain religions and\
                mythologies",
        "Angel Falls;90;waterfall in Venezuela; highest uninterrupted \
                waterfall in the world",
        "Angela Davis;70;American political activist, scholar, and author"
       ]

     URL:
      http://<host>:<port>/search.html?q=eyjaffjala
     RESPONSE:
      %QUERY%:
        eyjaffjala
      %RESULT%:
       ["Eyjafjallajökull;76;ice cap in Iceland covering the caldera of a \
                volcano",
        "Eyjafjallajökull;8;2013 film by Alexandre Coffre"
       ]

     URL:
      http://<host>:<port>/search.html?q=The+hitschheiker+guide
     RESPONSE:
      %QUERY%:
       The hitschheiker guide
      %RESULT%:
       ["The Hitchhiker's Guide to the Galaxy pentalogy;44;1979-1992 series\
                of five books by Douglas Adams",
        "The Hitchhiker's Guide to the Galaxy;43;1979 book by Douglas Adams",
        "The Hitchhiker's Guide to the Galaxy;36;2005 film directed by Garth \
                Jennings",
        "The Hitchhiker's Guide to the Galaxy;8;BBC television series",
        "The Hitchhiker's Guide to the Galaxy;7;1984 interactive fiction video\
                game"
       ]
    """

    def __init__(self, file_name: str, port: int, use_synonyms: bool):
        """
        Initialize with given port.
        """
        self.file_name = file_name
        self.port = port
        self.use_synonyms = use_synonyms

    def run(self):
        """
        Run the server loop: create a socket, and then, in an infinite loop,
        wait for requests and do something with them.
        """
        # Create server socket using IPv4 addresses and TCP.
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow reuse of port if we start program again after a crash.
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Say on which machine and port we want to listen for connections.
        server_address = ("0.0.0.0", self.port)
        server_socket.bind(server_address)
        # Start listening
        server_socket.listen()
        q, result = self.pre_query_search()

        while True:
            print()
            print("Waiting for Connection on ", self.port)
            connection, client_address = server_socket.accept()
            print("Client connected  from ", client_address)

            request_data = b""
            batch_size = 64
            while True:
                data_batch = connection.recv(batch_size)
                if len(data_batch) == 0:
                    break

                request_data += data_batch
                if request_data.find(b"\r\n\r\n") != -1:
                    break

            request = request_data.decode("utf-8").split("\r\n")[0]

            print(f"Request received :{request}\n")

            # Apply multiprocessing
            multiprocessing \
                .Process(target=self.handle_request_and_send_result,
                         args=[connection, request, q, result]).start()

            # Handle the request and send the result
            # self.result =
            # self.handle_request_and_send_result(connection, request)

    def pre_query_search(self):
        start = time.monotonic()
        q = qgram_index.QGramIndex(3, True)
        q.build_from_file(self.file_name)
        result = f"Done, took {(time.monotonic() - start) * 1000} ms.<br>"
        return q, result

    def query_search(self, q, query, result):
        print("query --------->  " + query)
        query = q.normalize(query)
        start = time.monotonic()

        # Process the keywords.
        delta = int(len(query) / 4)

        postings, _ = q.find_matches(query, delta)
        result += f"Got {len(postings)} result(s)," \
                  f" merged {q.merges[0]} lists with " + \
                  f"tot. {q.merges[1]} elements " \
                  f"({q.merge_time} ms), " + \
                  f"{q.ped_calcs[0]}/{q.ped_calcs[1]}" \
                  f" ped calculations ({q.ped_time} ms),took " \
                  f"{(time.monotonic() - start) * 1000} ms total."

        result += "<br><br>Top 5 result --<br>"
        result += "<table>"
        for ent in q.rank_matches(postings)[:5]:
            result += "<tr>"
            result += f"<td> {q.entities[ent[0] - 1][0]} (score=" + \
                      f"{ent[2]}, ped={ent[1]}, via " \
                      f"'{q.names[ent[3] - 1]}') </td><td>" + \
                      f"{q.entities[ent[0] - 1][2]}</td></tr>"
        result += "</table>"
        print(result)
        return str(result)

    def handle_request_and_send_result(self, connection, request, q, result):
        status, media_type, message = self.handle_request(request, q, result)

        if type(message) is str:
            message = message.encode("utf-8")

        # Send the result
        connection.sendall((f"HTTP/1.1 {status}\r\n"
                            f"Content-length: {len(message)}\r\n"
                            f"Content-type: {media_type}\r\n"
                            f"\r\n").encode("utf-8") + message)
        connection.close()

    def handle_request(self, request, q, result):
        print("request --> " + request)
        # ../ is used to check if it is going back from the server directory
        if not request.startswith("GET "):
            return "403 Go Away!!!", \
                   "text/plain", \
                   "We only support get requests"
        path = request.split(" ")[1]

        path = path[1:]

        query = ""
        pos = path.find("?query=")
        pos2 = path.find("&req_count=")
        req_count = -1
        if pos != -1:
            query = path[pos + 7:].split("&")[0]
            if pos2 != -1:
                req_count = path[pos2 + 11:]
            query = re.sub("%20", " ", query)
            # req_count = re.sub("%20", " ", req_count)
            query = unquote(query)

            path = path[:pos]
            print(f"Found query: {query}")
            print(f"Found req_count: {req_count}")

        print(f"Path: {path}")

        filep = Path(__file__).parent.absolute()

        if path == "api":
            try:

                if query:
                    result = self.query_search(q, query, result)
                    result = re.sub("\"", "\\\"'", result)
                    result = re.sub("\n", "", result)
                    result = "{\"result\":\"" + str(result) + \
                             "\",\"req_count\":\"" + str(req_count) + "\"}"

                # if re.match("^[0-9+*/ -]+$", query):
                #     time.sleep(random.random() * 2)
                #
                #     result = f"{{\"result\":{eval(query)}}}"
                else:
                    raise
            except Exception as e:
                result = f"{{\"result\":\"{str(e)}\"}}"

        else:
            try:
                filep = filep / Path(path)
                if not filep.is_file():
                    return "403 Go Away!", \
                           "text/plain", \
                           "We only support get requests"

                with open(path, "rb") as file:
                    result = file.read()
                    result = result.decode("utf-8")
            except Exception as e:
                return "404 Not Found", "text/plain", str(e)

        status = "200 OK"
        if path.endswith(".html"):
            media_type = "text/html"
        elif path.endswith(".css"):
            media_type = "text/css"
        elif path.endswith(".js"):
            media_type = "application/javascript"
        else:
            media_type = "text/plain"

        return status, media_type, result


def main():
    if len(sys.argv) < 3:
        print(f"Usage: python3 {sys.argv[0]} {sys.argv[1]}"
              + " <port> [--useSynonym]")
        sys.exit(1)
    file_name = str(sys.argv[1])
    port = int(sys.argv[2])
    use_synonyms = ""
    if len(sys.argv) == 4:
        use_synonyms = bool(sys.argv[3])
    server = SearchServer(file_name, port, use_synonyms)
    server.run()


if __name__ == "__main__":
    main()

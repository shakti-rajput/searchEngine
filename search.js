
function documentReady(){
    var req_count = 0;
    document.querySelector("#input").addEventListener("input",
    async function(){
        req_count +=1
        const query= document.querySelector("#input").value;
        console.log("Input action detected, input is:", query);
        response = await fetch("api?query="+query+"&req_count="+req_count)
                            .then(response => response.json());
        result = response["result"]
        console.log(req_count)
        console.log(response["req_count"])
        if (response["req_count"] == req_count){
            console.log("Result:\n",response);
            document.querySelector("#query").innerHTML = query
            document.querySelector("#result").innerHTML = result
        }
    })
}
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔥 Chat</title>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',sans-serif}
body{height:100vh;background:#0f0c29;color:white;display:flex}

/* Sidebar */
.sidebar{
  width:220px;
  background:#1f2024;
  padding:20px;
}
.sidebar h3{margin-bottom:20px}

/* Chat */
.chat{
  flex:1;
  display:flex;
  flex-direction:column;
  padding:20px;
}

#messages{
  flex:1;
  overflow-y:auto;
  display:flex;
  flex-direction:column;
  gap:8px;
}

.message{
  max-width:70%;
  padding:10px;
  border-radius:10px;
}

.mine{align-self:flex-end;background:#5865f2}
.other{align-self:flex-start;background:#444}

#chat-form{
  display:flex;
  gap:10px;
  margin-top:10px;
}

#msg{
  flex:1;
  padding:10px;
  border:none;
  border-radius:8px;
}

button{
  padding:10px;
  border:none;
  background:#5865f2;
  color:white;
  border-radius:8px;
  cursor:pointer;
}
</style>
</head>

<body>

<div class="sidebar">
  <h3>💬 Chat</h3>
  <p>👤 {{ username }}</p>
</div>

<div class="chat">
  <div id="messages"></div>
  <div id="typing"></div>

  <form id="chat-form">
    <input id="msg" placeholder="Type message..." autocomplete="off">
    <input type="file" id="file" hidden>
    <button type="button" onclick="document.getElementById('file').click()">📎</button>
    <button type="submit">Send</button>
  </form>
</div>

<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>

<script>
const username = {{ username | tojson }};
const socket = io();

let room = null;
const messages = document.getElementById("messages");
const input = document.getElementById("msg");

/* CONNECT */
socket.on("connect", () => {
    console.log("Connected");
    socket.emit("start_search");
});

/* MATCHED */
socket.on("matched", (data) => {
    room = data.room;
    addSystem("Connected to " + data.partner);
});

/* WAITING */
socket.on("waiting", () => {
    addSystem("Searching for partner...");
});

/* PARTNER LEFT */
socket.on("partner_left", () => {
    addSystem("Partner left. Searching again...");
    socket.emit("start_search");
});

/* SEND MESSAGE */
document.getElementById("chat-form").addEventListener("submit", e=>{
    e.preventDefault();
    if(!input.value.trim() || !room) return;

    socket.emit("send_message", {
        room: room,
        message: input.value
    });

    input.value="";
});

/* RECEIVE MESSAGE */
socket.on("new_message", msg => {
    addMessage(msg);
});

/* ADD MESSAGE */
function addMessage(msg){
    const div = document.createElement("div");
    div.className = "message " + (msg.sender === username ? "mine":"other");

    let content = "";

    if(msg.is_file){
        if(/\.(jpg|jpeg|png|gif|webp)$/i.test(msg.file_name)){
            content = `<img src="/uploads/${msg.file_name}" width="150">`;
        } else {
            content = `<a href="/uploads/${msg.file_name}" target="_blank">${msg.file_name}</a>`;
        }
    } else {
        content = msg.message;
    }

    div.innerHTML = `<small>${msg.sender}</small><br>${content}`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

/* SYSTEM MESSAGE */
function addSystem(text){
    const div = document.createElement("div");
    div.style.textAlign="center";
    div.style.opacity="0.6";
    div.innerText = text;
    messages.appendChild(div);
}

/* FILE UPLOAD */
document.getElementById("file").addEventListener("change", async ()=>{
    const file = document.getElementById("file").files[0];
    if(!file || !room) return;

    let form = new FormData();
    form.append("file", file);

    let res = await fetch("/upload", {method:"POST", body:form});
    let data = await res.json();

    if(!data.filename){
        alert("Upload failed");
        return;
    }

    socket.emit("send_file", {
        room: room,
        file_name: data.filename
    });
});

/* TYPING */
input.addEventListener("input", ()=>{
    socket.emit("typing", {room});
});

socket.on("typing", ()=>{
    document.getElementById("typing").innerText = "Typing...";
    setTimeout(()=>document.getElementById("typing").innerText="",1000);
});
</script>

</body>
</html>
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import socket from "@/services/socket";
import storeAuth from "@/stores/auth";
import { storeToRefs } from "pinia";

// Props
const route = useRoute();
const auth = storeAuth();
const { user } = storeToRefs(auth);
const imageUrl = ref("");
const sessionId = ref("");
const audioCtx = ref<AudioContext | null>(null);
const sampleRate = ref(0);
const keys: {[index: string]:number} = {
  "ArrowUp": 4,
  "ArrowDown": 5,
  "ArrowLeft": 6,
  "ArrowRight": 7,
  "KeyZ": 8,
  "KeyX": 0,
  "KeyA": 9,
  "KeyS": 1,
  "KeyQ": 10,
  "KeyE": 11,
  "Enter": 3,
  "Space": 2
}

socket.on("emulation:video", (msg) => {
  imageUrl.value = `data:image/png;base64,${msg["data"]}`;
});

socket.on("emulation:config", (msg) => {
  console.log(msg["data"]);
  sampleRate.value = msg["data"]["audio_sample"];
});

socket.on("emulation:audio", (msg) => {
  const data = new Int16Array(msg["data"])
  const numFrames = data.length / 2

  if (audioCtx.value == null) {
    console.log("No audio context")
    return;
  }

  if (sampleRate.value == 0) {
    return;
  }

  const audioBuffer = audioCtx.value.createBuffer(2, numFrames, sampleRate.value)
  const channelDataLeft = audioBuffer.getChannelData(0)
  const channelDataRight = audioBuffer.getChannelData(1)

  for (let i = 0, j = 0; i < data.length; i += 2, j++) {
    channelDataLeft[j] = data[i] / 32767
    channelDataRight[j] = data[i + 1] / 32767
  }

  // Create an AudioBufferSourceNode and play the audio
  const source = audioCtx.value.createBufferSource()
  source.buffer = audioBuffer;
  source.connect(audioCtx.value.destination);
  source.start(0);
});

socket.on("emulation:create", (msg) => {
  sessionId.value = msg["data"]
  socket.emit("emulation:run", {
    sessionId: sessionId.value
  });
});

function onKeyDown(event: any) {
  console.log(event)
  if (event.code in keys) {
    socket.emit("emulation:command", {
      sessionId: sessionId.value,
      data: {
        command: 1,
        data: keys[event.code]
      }
    });
  }
}

function onKeyUp(event: any) {
  console.log(event)
  if (event.code in keys) {
    socket.emit("emulation:command", {
      sessionId: sessionId.value,
      data: {
        command: 2,
        data: keys[event.code]
      }
    });
  }
}

function reset() {
  socket.emit("emulation:command", {
      sessionId: sessionId.value,
      data: {
        command: 3,
      }
    });
}

function play() {
  socket.emit("emulation:command", {
      sessionId: sessionId.value,
      data: {
        command: 4,
      }
    });
}

function pause() {
  socket.emit("emulation:command", {
      sessionId: sessionId.value,
      data: {
        command: 5,
      }
    });
}

function shutdown() {
  socket.emit("emulation:exit", {
      sessionId: sessionId.value,
      data: {}
    });
}

function shareSession() {
  const {origin} = window.location
  navigator.clipboard.writeText(origin+"/session/"+sessionId.value+"/ejs");
}

onMounted(async () => {
  if (!socket.connected) socket.connect();
  audioCtx.value = new window.AudioContext();
  if (route.params.rom === undefined) {
    socket.emit("emulation:join", {
      sessionId: route.params.sessionId
    });
  } else {
    socket.emit("emulation:create", {
      romId: route.params.rom
    });
  }

  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
});

onUnmounted(async () => {
  socket.emit("emulation:disconnect", {});
});
</script>

<template>
  <div class="container">
  <div class="image-wrapper"> 
    <img :src="imageUrl" alt="Your Image">
    <div class="overlay">
      <div class="controls">
        <button aria-label="Play" @click="play()">
          <v-tooltip
            activator="parent"
            location="top"
          >Resume emulation</v-tooltip>
          <v-icon
            icon="mdi-play"
            end
          ></v-icon></button> 
        <button aria-label="Pause" @click="pause()">
          <v-tooltip
            activator="parent"
            location="top"
          >Pause emulation</v-tooltip>
          <v-icon
            icon="mdi-pause"
            end
          ></v-icon>
        </button>
        <button aria-label="Rewind" @click="reset()">
          <v-tooltip
            activator="parent"
            location="top"
          >Restart session</v-tooltip>
          <v-icon
            icon="mdi-restart"
            end
          ></v-icon>
        </button>
        <button aria-label="Shutdown" @click="shutdown()">
          <v-tooltip
            activator="parent"
            location="top"
          >Shutdown the session</v-tooltip>
          <v-icon
            icon="mdi-power"
            end
          ></v-icon>
        </button>
        <button aria-label="Share Session" @click="shareSession()">
          <v-tooltip
            activator="parent"
            location="top"
          >Copy link to session</v-tooltip>
          <v-icon
            icon="mdi-share-variant"
            end
          >
          </v-icon>
        </button>
      </div>
    </div>
  </div>
</div>
</template>

<style>
.container {
  position: relative;
  width: 100%; 
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}

.image-wrapper {
  position: relative; 
  width: auto;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  overflow: hidden;
}

.image-wrapper img {
  height: 100%;
  width: auto;
  display: block;
}

.overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  opacity: 0;
  transition: opacity 0.3s ease;
  background-color: rgba(0, 0, 0, 0.5); 
  display: flex;
  justify-content:   
  flex-start;
  align-items: flex-end;
  padding: 10px;
}

.image-wrapper:hover .overlay {
  opacity: 1;
}

.controls button {
  background-color: transparent;
  border: none;
  color: white;
  font-size: 20px;
  cursor: pointer;
  margin-right: 10px;
}
</style>

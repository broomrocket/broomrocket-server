# Experimental ⚠ socket-based Broomrocket server

This repository contains an experimental socket server to integrate Broomrocket with any game engine or 3D software.

## Starting the server

This server is written in Python 3.11. To run it, please perform the following steps:

### Setting up a venv

We recommend setting up a venv first:

```
python -m venv venv
```

Then activate the venv. On Linux/MacOS:

```
source venv/bin/activate
```

On Windows/PowerShell:

```
venv\Scripts\Activate.ps1
```

### Installing the dependencies

You can install the dependencies by running:

```
pip install -r requirements.txt
```

### Starting the server

Start the server by running:

```
python server.py
```

The server will start on port 3333. Note, this is *not* an HTTP server, you cannot access it via your browser. You will
need to use a specific protocol client (see below).

**⚠ Note on security:** This server is not intended to be run on a publicly accessible network as it can grant
access to the local filesystem.

## Protocol

The protocol is request-response based. Both the client and the server can send requests and await responses. Multiple
request-response pairs can be in transit at any time.

On the write messages look like this:

| Name    | Data type                           | Explanation           |
|---------|-------------------------------------|-----------------------|
| Header  | 4-byte little-endian signed integer | Length of the payload |
| Payload | JSON-encoded payload                | See below             |

### JSON structure

All messages have 3 fields:

```json
{
  "type": "request|response",
  "id": "opaque message ID here",
  "data": {
    // Message data here.
    // May also be an array.
  }
}
```

As the name suggests, the response responds to the request with the same ID.

### Client request/response

The client only has the option to request a sentence to be parsed and executed. The data section of the message is as
follows:

```json
{
  "type": "request",
  "id": "opaque message ID here",
  "data": {
    "mesh_provider_id": "dummy|local|sketchfab",
    "mesh_provider_parameters": {
      // See below
    },
    "sentence": "Place a house"
  }
}
```

Each mesh provider has different parameters:

| Provider  | Parameter | Type   | Explanation                                 |
|-----------|-----------|--------|---------------------------------------------|
| local     | root      | string | Root directory to read the mesh files from. |
| sketchfab | apikey    | string | Sketchfab API key.                          |
| sketchfab | license   | string | Sketchfab license ID to use. (Optional)     |

The response to the client is as follows:

```json
{
  "type": "response",
  "id": "opaque message ID here",
  "data": {
    "status": "ok|error",
    "message": "Error message here."
  }
}
```

### Server requests and responses

The server has two requests it can send to the client in order to access the 3D scene. Again, keep in mind,
these requests happen before the server has responded to the client request.

#### List objects request/response

This request prompts the client to send all objects that are currently present in the 3D scene.

The request is simple:

```json
{
  "type": "request",
  "id": "opaque message ID here",
  "data": {
    "command": "list_objects"
  }
}
```

The response is somewhat more complex:

```json
{
  "type": "response",
  "id": "opaque message ID here",
  "data": [
    {
      "name": "mesh_name",
      "size": {
        "min_x": 0.0,
        "max_x": 1.0,
        "min_y": 0.0,
        "max_y": 1.0,
        "min_z": 0.0,
        "max_z": 1.0
      },
      "translation": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0
      }
    }
  ]
}
```

**⚠ Note:** Coordinates in Broomrocket are Z+ up!

#### Load GLTF request / response

This command instructs the client to load a GLTF file. The entire GLTF data set is sent over the wire.

The request is as follows:

```json
{
  "type": "request",
  "id": "opaque message ID here",
  "data": {
    "command": "load_gltf",
    "name": "new_mesh_name",
    "gltf": {
      "files": {
        "data.gltf": "GLTF data here",
        "license.txt": "License file here"
      },
      "gltf_file": "data.gltf",
      "license_file": "license.txt" // optional
    }
  }
}
```

The response is as follows:

```json
{
  "type": "response",
  "id": "opaque message ID here",
  "data": {
    "name": "new_mesh_name",
    "size": {
      "min_x": 0.0,
      "max_x": 1.0,
      "min_y": 0.0,
      "max_y": 1.0,
      "min_z": 0.0,
      "max_z": 1.0
    },
    "translation": {
      "x": 0.0,
      "y": 0.0,
      "z": 0.0
    }
  }
}
```

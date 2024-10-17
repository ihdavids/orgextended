import requests


def getUrl() -> str:
    url = sets.Get("orgsUrl", "https://localhost:443")
    return url


# class OrgS:
# 	def __init__(self):
# 		pass

# 	def post(self, body):
# 		url = getUrl()
# 		data = json.dumps(body)
# 		response = requests.post(url, data=data)

# 	def get(self, url, body):
# 		headers = {
# 			'Content-Type': 'application/json',
# 			'Accept': 'application/json'
# 		}

# 		pass



#    public static async doGet<T>(url: any): Promise<T> {
#         // We can use the `Headers` constructor to create headers
#         // and assign it as the type of the `headers` variable
#         const headers: Headers = new Headers()
#         // Add a few headers
#         headers.set('Content-Type', 'application/json')
#         headers.set('Accept', 'application/json')
#         // Add a custom header, which we can use to check
#         //headers.set('X-Custom-Header', 'CustomValue')
#         // Create the request object, which will be a RequestInfo type. 
#         // Here, we will pass in the URL as well as the options object as parameters.
#         if(url instanceof String) {
#             url = new URL(Sets.orgsConnection + url);
#         }
#         //const got = await import("got");
#         //var res = await got.get(url);
#         //return JSON.parse(res.body) as T;
     
#         var httpsAgent = https.globalAgent;
#         if (Sets.allowSelfSigned) {
#           httpsAgent = new https.Agent({
#                 rejectUnauthorized: false,
#           });
#         }
      
#         const request: RequestInfo = new Request(url, {
#             method: 'GET',
#             headers: headers,
#             agent: httpsAgent,
#         });
#         try{
#             // Pass in the request object to the `fetch` API
#             var res = await fetch(request);
#             return res.json() as T;
#         } catch(error) {
#             vscode.window.showErrorMessage(error.message)
#         }
#     }

#     public static async doPost<T>(url: any, payload: any): Promise<T> {
#         // We can use the `Headers` constructor to create headers
#         // and assign it as the type of the `headers` variable
#         const headers: Headers = new Headers()
#         // Add a few headers
#         headers.set('Content-Type', 'application/json')
#         // We also need to set the `Accept` header to `application/json`
#         // to tell the server that we expect JSON in response
#         headers.set('Accept', 'application/json')

#         if(url instanceof String) {
#             url = new URL(Sets.orgsConnection + url);
#         }

#         var httpsAgent = https.globalAgent;
#         if (Sets.allowSelfSigned) {
#           httpsAgent = new https.Agent({
#                 rejectUnauthorized: false,
#           });
#         }

#         const request: RequestInfo = new Request(url, {
#             // We need to set the `method` to `POST` and assign the headers
#             method: 'POST',
#             headers: headers,
#             // Convert the user object to JSON and pass it as the body
#             body: JSON.stringify(payload),
#             agent: httpsAgent,
#         });

#         try{
#             var res = await fetch(request);
#             const js = res.json();
#             return js as T;
#         } catch(error) {
#             vscode.window.showErrorMessage("POST FAILED: " + error.message)
#         }
#     }

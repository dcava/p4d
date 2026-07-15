/*
  +----------------------------------------------------------------------+
  | lib4D_SQL                                                            |
  +----------------------------------------------------------------------+
  | Copyright (c) 2009 The PHP Group                                     |
  +----------------------------------------------------------------------+
  |                                                                      |
  | This source file is subject to version 3.01 of the PHP license,      |
  | that is bundled with this package in the file LICENSE, and is        |
  | available through the world-wide-web at the following url:           |
  | http://www.php.net/license/3_01.txt                                  |
  |                                                                      |
  | Its original copy is usable under several licenses and is available  |
  | through the world-wide-web at the following url:                     |
  | http://freshmeat.net/projects/lib4d_sql                              |
  |                                                                      |
  | Unless required by applicable law or agreed to in writing, software  |
  | distributed under the License is distributed on an "AS IS" BASIS,    |
  | WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or      |
  | implied. See the License for the specific language governing         |
  | permissions and limitations under the License.                       |
  +----------------------------------------------------------------------+
  | Contributed by: 4D <php@4d.fr>, http://www.4d.com                    |
  |                 Alter Way, http://www.alterway.fr                    |
  | Authors: Stephane Planquart <stephane.planquart@o4db.com>            |
  |          Alexandre Morgaut <php@4d.fr>                               |
  +----------------------------------------------------------------------+
*/

#include "fourd.h"
#include "fourd_int.h"
#include "base64.h"
#include <sys/select.h>
#include <string.h>
#include <time.h>
#ifdef WIN32
#define EINPROGRESS WSAEWOULDBLOCK
#else
#include <fcntl.h>
#endif

/* Refill the connection read buffer with whatever the socket has.
   Returns the number of bytes read, or -1 on error/close. */
static long rbuf_fill(FOURD *cnx)
{
	long r;
	cnx->rbuf_pos=0;
	cnx->rbuf_len=0;
	r=recv(cnx->socket,(char*)cnx->rbuf,cnx->rbuf_size,0);
	if(r<=0){
		return -1;
	}
	cnx->rbuf_len=(unsigned int)r;
	return r;
}

/* Read exactly len bytes through the connection buffer.
   Returns 0 on success, -1 on error/close (connection unusable). */
static int buf_recv(FOURD *cnx,void *dst,size_t len)
{
	unsigned char *out=dst;
	size_t copied=0;
	while(copied<len){
		size_t avail=cnx->rbuf_len-cnx->rbuf_pos;
		if(avail==0){
			size_t remaining=len-copied;
			if(remaining>=cnx->rbuf_size){
				/* large read (blob/string body): receive straight into dst */
				size_t chunk=remaining>0x40000000?0x40000000:remaining;
				long r=recv(cnx->socket,(char*)out+copied,(int)chunk,0);
				if(r<=0){
					return -1;
				}
				copied+=(size_t)r;
				continue;
			}
			if(rbuf_fill(cnx)<0){
				return -1;
			}
			continue;
		}
		{
			size_t take=(avail<len-copied)?avail:len-copied;
			memcpy(out+copied,cnx->rbuf+cnx->rbuf_pos,take);
			cnx->rbuf_pos+=(unsigned int)take;
			copied+=take;
		}
	}
	return 0;
}

/* Record a connection-level read failure on both the result and the cnx. */
static int read_failed(FOURD *cnx,FOURD_RESULT *state)
{
	if(state!=NULL){
		state->status=FOURD_ERROR;
		if(state->error_code==0){
			state->error_code=-1;
			sprintf_s(state->error_string,ERROR_STRING_LENGTH,"Connection lost while reading from server");
		}
		cnx->error_code=state->error_code;
		strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,state->error_string,ERROR_STRING_LENGTH);
	}
	else if(cnx->error_code==0){
		cnx->error_code=-1;
		sprintf_s(cnx->error_string,ERROR_STRING_LENGTH,"Connection lost while reading from server");
	}
	cnx->status=FOURD_ERROR;
	return 1;
}

int socket_connect(FOURD *cnx,const char *host,unsigned int port)
{
	//WSADATA wsaData;
	
	struct addrinfo *result = NULL,
					*ptr = NULL,
					hints;
	int iResult=0;
	//SOCKET ConnectSocket = INVALID_SOCKET;

	char sport[50];
	sprintf_s(sport,50,"%d",port);

	/*
	// Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
    if (iResult != 0) {
        Printf("WSAStartup failed: %d\n", iResult);
        return 1;
    }
	*/

	//initialize Hints
	ZeroMemory( &hints, sizeof(hints) );
	hints.ai_family = AF_INET;
	hints.ai_socktype = SOCK_STREAM;
	hints.ai_protocol = IPPROTO_TCP;

	// Resolve the server address and port
	iResult = getaddrinfo(host, sport, &hints, &result);
	if ( iResult != 0 ) {
		Printf("getaddrinfo failed: %d : %s\n", iResult,gai_strerror(iResult));
		cnx->error_code=-iResult;
		strncpy_s(cnx->error_string,2048,gai_strerror(iResult),2048);
		return 1;
	}
	//Printf("getaddrinfo ok\n");

		
	// Attempt to connect to the first address returned by
	// the call to getaddrinfo
	ptr=result;

	// Create a SOCKET for connecting to server
	cnx->socket = socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol);
	if (cnx->socket == INVALID_SOCKET) {
		Printf("Error at socket(): %ld\n", WSAGetLastError());
		cnx->error_code=-WSAGetLastError();
		strncpy_s(cnx->error_string,2048,"Unable to create socket",2048);
		freeaddrinfo(result);
		return 1;
	}
	//Printf("Socket Ok\n");
	// Connect to server.
	iResult = connect( cnx->socket, ptr->ai_addr, (int)ptr->ai_addrlen);
	if (iResult == SOCKET_ERROR) {
		Printf("Error at socket(): %ld\n", WSAGetLastError());
		cnx->error_code=-WSAGetLastError();
		strncpy_s(cnx->error_string,2048,"Unable to connect to server",2048);
		freeaddrinfo(result);
		closesocket(cnx->socket);
		cnx->socket = INVALID_SOCKET;
		return 1;
	}
	//Printf("Connexion ok\n");



	
	// Should really try the next address returned by getaddrinfo
	// if the connect call failed
	// But for this simple example we just free the resources
	// returned by getaddrinfo and print an error message

	freeaddrinfo(result);

	if (cnx->socket == INVALID_SOCKET) {
		Printf("Unable to connect to server!\n");
		cnx->error_code=-1;
		strncpy_s(cnx->error_string,2048,"Unable to connect to server",2048);
		return 1;
	}
	//Printf("fin de la fonction\n");

	/* discard any stale buffered bytes from a previous connection */
	cnx->rbuf_pos=0;
	cnx->rbuf_len=0;

	return 0;
}

void socket_disconnect(FOURD *cnx)
{
	// shutdown the send half of the connection since no more data will be sent
	#ifdef WIN32
	iResult = shutdown(cnx->socket, SD_SEND);
	if (iResult == SOCKET_ERROR) {
		Printf("shutdown failed: %d\n", WSAGetLastError());
		closesocket(cnx->socket);
		cnx->connected=0;
		return ;
	}
	#endif
	closesocket(cnx->socket);
	cnx->connected=0;
	//Printf("Disconnect ok\n");
}

/* Send exactly len bytes, handling partial sends. 0 on success, 1 on error. */
static int send_all(FOURD *cnx,const char *buf,size_t len)
{
	size_t sent=0;
	while(sent<len){
		size_t chunk=len-sent;
		long iResult;
		if(chunk>0x40000000)
			chunk=0x40000000;
		iResult=send(cnx->socket,buf+sent,(int)chunk,0);
		if(iResult==SOCKET_ERROR || iResult<0){
			Printf("send failed: %d\n", WSAGetLastError());
			cnx->error_code=-1;
			strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,"Connection lost while sending to server",ERROR_STRING_LENGTH);
			socket_disconnect(cnx);
			return 1;
		}
		sent+=(size_t)iResult;
	}
	return 0;
}

int socket_send(FOURD *cnx,const char*msg)
{
	Printf("Send:\n%s",msg);
	return send_all(cnx,msg,strlen(msg));
}
int socket_send_data(FOURD *cnx,const char*msg,int len)
{
	Printf("Send:%d bytes\n",len);
	PrintData(msg,len);
	Printf("\n");
	if(len<0)
		return 1;
	return send_all(cnx,msg,(size_t)len);
}

int socket_receiv_header(FOURD *cnx,FOURD_RESULT *state)
{
	unsigned int len=0;
	unsigned int size=4096;
	char *hdr=NULL;

	state->header=NULL;
	state->header_size=0;

	hdr=malloc(size);
	if(hdr==NULL){
		cnx->error_code=-1;
		strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,"Out of memory reading response header",ERROR_STRING_LENGTH);
		return 1;
	}

	/* Consume from the connection buffer until \r\n\r\n; any bytes past the
	   terminator stay buffered for socket_receiv_data. */
	for(;;){
		if(cnx->rbuf_pos>=cnx->rbuf_len){
			if(rbuf_fill(cnx)<0){
				free(hdr);
				return read_failed(cnx,NULL);
			}
		}
		if(len+2>size){
			char *tmp=NULL;
			if(size>=FOURD_MAX_HEADER_SIZE){
				free(hdr);
				cnx->error_code=-1;
				strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,"Response header exceeds maximum size",ERROR_STRING_LENGTH);
				return 1;
			}
			size*=2;
			tmp=realloc(hdr,size);
			if(tmp==NULL){
				free(hdr);
				cnx->error_code=-1;
				strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,"Out of memory reading response header",ERROR_STRING_LENGTH);
				return 1;
			}
			hdr=tmp;
		}
		hdr[len++]=(char)cnx->rbuf[cnx->rbuf_pos++];
		if(len>=4 && memcmp(hdr+len-4,"\r\n\r\n",4)==0)
			break;
	}

	hdr[len]=0;
	state->header=hdr;
	state->header_size=len;
	Printf("Receiv:\n%s",state->header);
	return 0;
}
/* Record a malformed-stream error. The stream position is lost, so the
   connection must not be reused for further commands on this statement. */
static int proto_failed(FOURD *cnx,FOURD_RESULT *state,const char *what,unsigned int row,unsigned int col)
{
	state->status=FOURD_ERROR;
	if(state->error_code==0)
		state->error_code=-1;
	sprintf_s(state->error_string,ERROR_STRING_LENGTH,"%s at row %u column %u",what,row+1,col+1);
	cnx->error_code=state->error_code;
	strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,state->error_string,ERROR_STRING_LENGTH);
	cnx->status=FOURD_ERROR;
	return 1;
}
static int oom_failed(FOURD *cnx,FOURD_RESULT *state)
{
	state->status=FOURD_ERROR;
	state->error_code=-1;
	sprintf_s(state->error_string,ERROR_STRING_LENGTH,"Out of memory reading result data");
	cnx->error_code=state->error_code;
	strncpy_s(cnx->error_string,ERROR_STRING_LENGTH,state->error_string,ERROR_STRING_LENGTH);
	cnx->status=FOURD_ERROR;
	return 1;
}

int socket_receiv_data(FOURD *cnx,FOURD_RESULT *state)
{
	unsigned int nbCol=state->row_type.nbColumn;
	unsigned int nbRow=state->row_count_sent;
	unsigned int r,c;
	FOURD_TYPE *colType=NULL;
	FOURD_ELEMENT *pElmt=NULL;
	unsigned char status_code=0;
	size_t elmts_offset=0;
	int ret=0;

	Printf("---Debut de socket_receiv_data\n");
	if(nbCol==0 || nbRow==0){
		state->elmt=NULL;
		return 0;
	}
	if(state->row_type.Column==NULL)
		return proto_failed(cnx,state,"Result data received without column metadata",0,0);

	colType=malloc((size_t)nbCol*sizeof(FOURD_TYPE));
	if(colType==NULL)
		return oom_failed(cnx,state);
	for(c=0;c<nbCol;c++)
		colType[c]=state->row_type.Column[c].type;

	/* calloc checks nbCol*nbRow overflow internally and returns NULL */
	state->elmt=calloc((size_t)nbCol*(size_t)nbRow,sizeof(FOURD_ELEMENT));
	if(state->elmt==NULL){
		free(colType);
		return oom_failed(cnx,state);
	}

	Printf("state->row_count:%d\t\tstate->row_count_sent:%d\n",state->row_count,state->row_count_sent);
	for(r=0;r<nbRow;r++)
	{
		/* read status_code and row_id (sent only for updateable rows) */
		if(state->updateability)
		{
			if(buf_recv(cnx,&status_code,1)!=0){ret=read_failed(cnx,state);goto done;}
			switch(status_code)
			{
			case '0':
				break;
			case '1':
			{
				int row_id=0;
				if(buf_recv(cnx,&row_id,sizeof(row_id))!=0){ret=read_failed(cnx,state);goto done;}
				break;
			}
			case '2':
				buf_recv(cnx,&(state->error_code),sizeof(state->error_code));
				ret=proto_failed(cnx,state,"Server reported error in row data",r,0);
				goto done;
			default:
				ret=proto_failed(cnx,state,"Unsupported row status code",r,0);
				goto done;
			}
		}

		/* read all columns */
		for(c=0;c<nbCol;c++,elmts_offset++)
		{
			pElmt=&(state->elmt[elmts_offset]);
			pElmt->type=colType[c];

			if(buf_recv(cnx,&status_code,1)!=0){ret=read_failed(cnx,state);goto done;}
			if(status_code=='0'){		/* null value */
				pElmt->null=1;
				continue;
			}
			if(status_code=='2'){		/* server-side error */
				buf_recv(cnx,&(state->error_code),sizeof(state->error_code));
				ret=proto_failed(cnx,state,"Server reported error in column data",r,c);
				goto done;
			}
			if(status_code!='1'){
				ret=proto_failed(cnx,state,"Unsupported column status code",r,c);
				goto done;
			}
			pElmt->null=0;
			switch(colType[c])
			{
				case VK_BOOLEAN:
				case VK_BYTE:
				case VK_WORD:
				case VK_LONG:
				case VK_LONG8:
				case VK_REAL:
				case VK_DURATION:
				{
					size_t sz=(size_t)vk_sizeof(colType[c]);
					pElmt->pValue=_arena_alloc(state,sz);
					if(pElmt->pValue==NULL){ret=oom_failed(cnx,state);goto done;}
					if(buf_recv(cnx,pElmt->pValue,sz)!=0){ret=read_failed(cnx,state);goto done;}
					break;
				}
				case VK_TIMESTAMP:
				{
					FOURD_TIMESTAMP *tmp=_arena_alloc(state,sizeof(FOURD_TIMESTAMP));
					if(tmp==NULL){ret=oom_failed(cnx,state);goto done;}
					pElmt->pValue=tmp;
					if(buf_recv(cnx,&(tmp->year),sizeof(int16_t))!=0
					|| buf_recv(cnx,&(tmp->mounth),1)!=0
					|| buf_recv(cnx,&(tmp->day),1)!=0
					|| buf_recv(cnx,&(tmp->milli),sizeof(uint32_t))!=0){
						ret=read_failed(cnx,state);goto done;
					}
					break;
				}
				case VK_FLOAT:
				{
					FOURD_FLOAT *tmp=_arena_alloc(state,sizeof(FOURD_FLOAT));
					if(tmp==NULL){ret=oom_failed(cnx,state);goto done;}
					tmp->data=NULL;
					pElmt->pValue=tmp;
					if(buf_recv(cnx,&(tmp->exp),sizeof(int32_t))!=0
					|| buf_recv(cnx,&(tmp->sign),1)!=0
					|| buf_recv(cnx,&(tmp->data_length),sizeof(int32_t))!=0){
						ret=read_failed(cnx,state);goto done;
					}
					if(tmp->data_length<0 || tmp->data_length>FOURD_MAX_FLOAT_BYTES){
						ret=proto_failed(cnx,state,"Malformed FLOAT length received",r,c);
						goto done;
					}
					if(tmp->data_length>0){
						tmp->data=_arena_alloc(state,(size_t)tmp->data_length);
						if(tmp->data==NULL){ret=oom_failed(cnx,state);goto done;}
						if(buf_recv(cnx,tmp->data,(size_t)tmp->data_length)!=0){ret=read_failed(cnx,state);goto done;}
					}
					break;
				}
				case VK_STRING:
				{
					int32_t data_length=0;
					FOURD_STRING *str=_arena_alloc(state,sizeof(FOURD_STRING));
					if(str==NULL){ret=oom_failed(cnx,state);goto done;}
					pElmt->pValue=str;
					if(buf_recv(cnx,&data_length,4)!=0){ret=read_failed(cnx,state);goto done;}
					/* string lengths arrive negated (UTF-16 char count) */
					if(data_length>0 || data_length==INT32_MIN){
						ret=proto_failed(cnx,state,"Malformed string length received",r,c);
						goto done;
					}
					data_length=-data_length;
					if(data_length>FOURD_MAX_STRING_CHARS){
						ret=proto_failed(cnx,state,"String length exceeds maximum",r,c);
						goto done;
					}
					str->length=data_length;
					str->data=_arena_alloc(state,(size_t)data_length*2+2);
					if(str->data==NULL){ret=oom_failed(cnx,state);goto done;}
					if(data_length>0
					&& buf_recv(cnx,str->data,(size_t)data_length*2)!=0){
						ret=read_failed(cnx,state);goto done;
					}
					str->data[(size_t)data_length*2]=0;
					str->data[(size_t)data_length*2+1]=0;
					break;
				}
				case VK_IMAGE:
				case VK_BLOB:
				{
					int32_t data_length=0;
					FOURD_BLOB *blob=_arena_alloc(state,sizeof(FOURD_BLOB));
					if(blob==NULL){ret=oom_failed(cnx,state);goto done;}
					pElmt->pValue=blob;
					if(buf_recv(cnx,&data_length,4)!=0){ret=read_failed(cnx,state);goto done;}
					if(data_length<0 || data_length>FOURD_MAX_BLOB_BYTES){
						ret=proto_failed(cnx,state,"Malformed BLOB length received",r,c);
						goto done;
					}
					if(data_length==0){
						blob->length=0;
						blob->data=NULL;
						pElmt->null=1;
					}else{
						blob->data=_arena_alloc(state,(size_t)data_length);
						if(blob->data==NULL){ret=oom_failed(cnx,state);goto done;}
						blob->length=data_length;
						if(buf_recv(cnx,blob->data,(size_t)data_length)!=0){ret=read_failed(cnx,state);goto done;}
					}
					break;
				}
				default:
					/* unknown wire type: its size is unknown, the stream
					   cannot be resynchronised — abort instead of desyncing */
					ret=proto_failed(cnx,state,"Unsupported column type in result data",r,c);
					goto done;
			}
		}
	}
	Printf("---Fin de socket_receiv_data\n");
done:
	free(colType);
	return ret;
}
int socket_receiv_update_count(FOURD *cnx,FOURD_RESULT *state)
{
	FOURD_LONG8 data=0;
	if(buf_recv(cnx,&data,8)!=0)
		return read_failed(cnx,state);
	cnx->updated_row=data;

	return 0;
}
int set_sock_blocking(int socketd, int block)
{
	int ret = 0;
	int flags;
	int myflag = 0;

#ifdef WIN32
	/* with ioctlsocket, a non-zero sets nonblocking, a zero sets blocking */
	flags = !block;
	if (ioctlsocket(socketd, FIONBIO, &flags) == SOCKET_ERROR) {
		/*char *error_string;
		
		error_string = php_socket_strerror(WSAGetLastError(), NULL, 0);
		php_error_docref(NULL TSRMLS_CC, E_WARNING, "%s", error_string);
		efree(error_string);*/
		ret = 1;
	}
#else
	flags = fcntl(socketd, F_GETFL);
#ifdef O_NONBLOCK
	myflag = O_NONBLOCK; /* POSIX version */
#elif defined(O_NDELAY)
	myflag = O_NDELAY;   /* old non-POSIX version */
#endif
	if (!block) {
		flags |= myflag;
	} else {
		flags &= ~myflag;
	}
	fcntl(socketd, F_SETFL, flags);
#endif
	return ret;
}

int socket_connect_timeout(FOURD *cnx,const char *host,unsigned int port,int timeout)
{
	//WSADATA wsaData;
	
	struct addrinfo *result = NULL,
					*ptr = NULL,
					hints;
	int iResult=0,valopt=0;
	/*SOCKET ConnectSocket = INVALID_SOCKET; */
	struct timeval tv; 
	fd_set myset; 
	socklen_t lon;
	
	//int nbTryConnect=0;
	char sport[50];
	sprintf_s(sport,50,"%d",port);

	/*
	Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
    if (iResult != 0) {
        Printf("WSAStartup failed: %d\n", iResult);
        return 1;
    }
	*/

	/* initialize Hints */
	ZeroMemory( &hints, sizeof(hints) );
	hints.ai_family = AF_INET;
	hints.ai_socktype = SOCK_STREAM;
	hints.ai_protocol = IPPROTO_TCP;

	/* Resolve the server address and port */
	iResult = getaddrinfo(host, sport, &hints, &result);
	if ( iResult != 0 ) {
		Printf("getaddrinfo failed: %d : %s\n", iResult,gai_strerror(iResult));
		cnx->error_code=-iResult;
		strncpy_s(cnx->error_string,2048,gai_strerror(iResult),2048);
		return 1;
	}
	/* Printf("getaddrinfo ok\n"); */

		
	/*Attempt to connect to the first address returned by
	 the call to getaddrinfo */
	ptr=result;

	/* Create a SOCKET for connecting to server */
	cnx->socket = socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol);
	if (cnx->socket == INVALID_SOCKET) {
		Printf("Error at socket(): %ld\n", WSAGetLastError());
		cnx->error_code=-WSAGetLastError();
		strncpy_s(cnx->error_string,2048,"Unable to create socket",2048);
		freeaddrinfo(result);
		return 1;
	}
	int flag=1;
	// if we get an error here, we can safely ignore it. The connection may be slower, but it should
	// still work.
	setsockopt(cnx->socket, IPPROTO_TCP, TCP_NODELAY, (char *)&flag, sizeof(int));
	
	/* Printf("Socket Ok\n"); */
	/*set Non blocking socket */
	set_sock_blocking(cnx->socket,0);
	/* Connect to server. */
	iResult = connect( cnx->socket, ptr->ai_addr, (int)ptr->ai_addrlen);
	if(iResult<0){
		if (WSAGetLastError() == EINPROGRESS) { 
        tv.tv_sec = timeout; 
        tv.tv_usec = 0; 
        FD_ZERO(&myset); 
        FD_SET(cnx->socket, &myset); 
        if (select(cnx->socket+1, NULL, &myset, NULL, &tv) > 0) { 
					lon = sizeof(int); 
					getsockopt(cnx->socket, SOL_SOCKET, SO_ERROR, (void*)(&valopt), &lon); 
					if (valopt) { 
						fprintf(stderr, "Error in connection() %d - %s\n", valopt, strerror(valopt));
						cnx->error_code=valopt;
						strncpy_s(cnx->error_string,2048,strerror(valopt),2048);
						freeaddrinfo(result);
						closesocket(cnx->socket);
						cnx->socket = INVALID_SOCKET;
						return 1;
					} 
					/*connection ok*/
        } 
        else { 
			/*fprintf(stderr, "Timeout or error() %d - %s\n", valopt, strerror(valopt)); */
			cnx->error_code=3011;
			strncpy_s(cnx->error_string,2048,"Connect timed out",2048);
			freeaddrinfo(result);
			closesocket(cnx->socket);
			cnx->socket = INVALID_SOCKET;
			return 1;
        } 
     } 
     else {
        cnx->error_code=-WSAGetLastError();
        snprintf(cnx->error_string, 2048, "Error connecting: %s", strerror(WSAGetLastError()));
			freeaddrinfo(result);
			closesocket(cnx->socket);
			cnx->socket = INVALID_SOCKET;
        return 1;
     } 

		
	}
		
	/* Printf("Connexion ok\n"); */


	/*set blocking socket */
	set_sock_blocking(cnx->socket,1);

	
	/* Should really try the next address returned by getaddrinfo
	   if the connect call failed
	   But for this simple example we just free the resources
	   returned by getaddrinfo and print an error message */

	freeaddrinfo(result);

	if (cnx->socket == INVALID_SOCKET) {
		Printf("Unable to connect to server!\n");
		cnx->error_code=-1;
		strncpy_s(cnx->error_string,2048,"Unable to connect to server",2048);
		return 1;
	}
	/* Printf("fin de la fonction\n"); */

	/* discard any stale buffered bytes from a previous connection */
	cnx->rbuf_pos=0;
	cnx->rbuf_len=0;

	return 0;
}

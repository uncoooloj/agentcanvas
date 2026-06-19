package main

import (
	"fmt"
	"net/http"

	_ "github.com/acme/audit"
	mux "github.com/gorilla/mux"
)

type Server struct {
	router *mux.Router
}

func main() {
	router := mux.NewRouter()
	server := &Server{router: router}

	router.HandleFunc("/health", healthHandler).Methods("GET")
	router.HandleFunc("/users/{id}", server.deleteUser).Methods("DELETE")
	http.HandleFunc("/ready", healthHandler)

	if err := run(); err != nil {
		fmt.Println("if this appears, it should not create a branch")
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	fmt.Println("healthy")
}

func (s *Server) deleteUser(w http.ResponseWriter, r *http.Request) {
	s.auditDelete()
}

func (s *Server) auditDelete() {}

func run() error {
	return nil
}

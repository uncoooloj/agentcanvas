Rails.application.routes.draw do
  root "home#index"
  resources :users
  get "/health", to: "health#show"

  # get "/commented", to: "nope#show"
end

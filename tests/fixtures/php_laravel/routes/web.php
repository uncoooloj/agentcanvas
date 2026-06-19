<?php

use App\Http\Controllers\{UserController, ReportController as Reports};
use function App\Support\route_metric;

Route::get('/users', [UserController::class, 'index']);
Route::match(['get', 'post'], '/reports', [ReportController::class, 'store']);
$router->delete('/users/{user}', 'UserController@destroy');

// Route::get('/commented-slash', 'Nope@index');
# Route::post('/commented-hash', 'Nope@store');

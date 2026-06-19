<?php

namespace App\Http\Controllers;

class UserController
{
    public function index($request)
    {
        if ($request->query('preview')) {
            return $this->preview();
        } elseif ($request->query('archived')) {
            return $this->archived();
        }

        return $this->allUsers();
    }

    public function destroy($user)
    {
        return $this->deleteUser($user);
    }
}

class ReportController
{
    public function store($request)
    {
        return route_metric($request);
    }
}

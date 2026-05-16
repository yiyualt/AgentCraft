package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"math/rand"
	"net"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	pb "examples/grpc-service/proto/user/v1"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"
)

// 自定义业务错误
var (
	ErrUserNotFound      = errors.New("user not found")
	ErrInvalidUserID     = errors.New("invalid user id")
	ErrInvalidEmail      = errors.New("invalid email format")
	ErrInvalidAge        = errors.New("age must be between 0 and 150")
	ErrNameRequired      = errors.New("name is required")
	ErrEmailAlreadyExist = errors.New("email already exists")
)

// userStore 内存用户存储（线程安全）
type userStore struct {
	mu     sync.RWMutex
	users  map[string]*pb.User
	nextID int
}

func newUserStore() *userStore {
	return &userStore{
		users:  make(map[string]*pb.User),
		nextID: 1,
	}
}

func (s *userStore) generateID() string {
	s.nextID++
	return fmt.Sprintf("u-%06d", s.nextID-1)
}

func (s *userStore) now() int64 {
	return time.Now().Unix()
}

func (s *userStore) Create(name, email string, age int32, phone string) (*pb.User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 检查 email 是否已存在
	for _, u := range s.users {
		if u.Email == email {
			return nil, ErrEmailAlreadyExist
		}
	}

	now := s.now()
	user := &pb.User{
		Id:        s.generateID(),
		Name:      name,
		Email:     email,
		Age:       age,
		Phone:     phone,
		CreatedAt: now,
		UpdatedAt: now,
	}
	s.users[user.Id] = user
	return user, nil
}

func (s *userStore) Get(id string) (*pb.User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	user, ok := s.users[id]
	if !ok {
		return nil, ErrUserNotFound
	}
	return user, nil
}

func (s *userStore) List(page, pageSize int32, keyword string) ([]*pb.User, int32, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// 先过滤
	var filtered []*pb.User
	for _, u := range s.users {
		if keyword != "" {
			// 关键词匹配 name 或 email
			if !contains(u.Name, keyword) && !contains(u.Email, keyword) {
				continue
			}
		}
		filtered = append(filtered, u)
	}

	total := int32(len(filtered))

	// 分页
	start := (page - 1) * pageSize
	if start >= total {
		return nil, total, nil
	}
	end := start + pageSize
	if end > total {
		end = total
	}

	return filtered[start:end], total, nil
}

func (s *userStore) Update(id, name, email string, age int32, phone string) (*pb.User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	user, ok := s.users[id]
	if !ok {
		return nil, ErrUserNotFound
	}

	// 检查 email 是否被其他用户占用
	for _, u := range s.users {
		if u.Id != id && u.Email == email {
			return nil, ErrEmailAlreadyExist
		}
	}

	user.Name = name
	user.Email = email
	user.Age = age
	user.Phone = phone
	user.UpdatedAt = s.now()
	return user, nil
}

func (s *userStore) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.users[id]; !ok {
		return ErrUserNotFound
	}
	delete(s.users, id)
	return nil
}

func contains(s, substr string) bool {
	return len(substr) == 0 || s != "" && substr != "" && containsSubstring(s, substr)
}

func containsSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		match := true
		for j := 0; j < len(substr); j++ {
			if s[i+j] != substr[j] {
				match = false
				break
			}
		}
		if match {
			return true
		}
	}
	return false
}

// userServiceServer 实现 UserServiceServer 接口
type userServiceServer struct {
	pb.UnimplementedUserServiceServer
	store *userStore
}

func newUserServiceServer(store *userStore) *userServiceServer {
	return &userServiceServer{store: store}
}

// validateGetUser 验证 GetUser 请求
func validateGetUser(req *pb.GetUserRequest) error {
	var errs []error
	if req.Id == "" {
		errs = append(errs, fmt.Errorf("id: %w", ErrInvalidUserID))
	}
	return errors.Join(errs...)
}

// validateCreateUser 验证 CreateUser 请求
func validateCreateUser(req *pb.CreateUserRequest) error {
	var errs []error
	if req.Name == "" {
		errs = append(errs, fmt.Errorf("name: %w", ErrNameRequired))
	}
	if !isValidEmail(req.Email) {
		errs = append(errs, fmt.Errorf("email: %w", ErrInvalidEmail))
	}
	if req.Age < 0 || req.Age > 150 {
		errs = append(errs, fmt.Errorf("age: %w", ErrInvalidAge))
	}
	return errors.Join(errs...)
}

// validateUpdateUser 验证 UpdateUser 请求
func validateUpdateUser(req *pb.UpdateUserRequest) error {
	var errs []error
	if req.Id == "" {
		errs = append(errs, fmt.Errorf("id: %w", ErrInvalidUserID))
	}
	if req.Name == "" {
		errs = append(errs, fmt.Errorf("name: %w", ErrNameRequired))
	}
	if !isValidEmail(req.Email) {
		errs = append(errs, fmt.Errorf("email: %w", ErrInvalidEmail))
	}
	if req.Age < 0 || req.Age > 150 {
		errs = append(errs, fmt.Errorf("age: %w", ErrInvalidAge))
	}
	return errors.Join(errs...)
}

// validateDeleteUser 验证 DeleteUser 请求
func validateDeleteUser(req *pb.DeleteUserRequest) error {
	var errs []error
	if req.Id == "" {
		errs = append(errs, fmt.Errorf("id: %w", ErrInvalidUserID))
	}
	return errors.Join(errs...)
}

// isValidEmail 简单验证 email 格式
func isValidEmail(email string) bool {
	if len(email) < 3 || len(email) > 254 {
		return false
	}
	atIndex := -1
	for i, c := range email {
		if c == '@' {
			atIndex = i
			break
		}
	}
	if atIndex < 1 || atIndex >= len(email)-1 {
		return false
	}
	// 检查 @ 后是否有点
	dotAfterAt := false
	for i := atIndex + 1; i < len(email); i++ {
		if email[i] == '.' {
			dotAfterAt = true
			break
		}
	}
	return dotAfterAt
}

// mapError 将业务错误映射为 gRPC 状态码
func mapError(err error) error {
	if err == nil {
		return nil
	}

	switch {
	case errors.Is(err, ErrUserNotFound):
		return status.Error(codes.NotFound, err.Error())
	case errors.Is(err, ErrInvalidUserID):
		return status.Error(codes.InvalidArgument, err.Error())
	case errors.Is(err, ErrInvalidEmail):
		return status.Error(codes.InvalidArgument, err.Error())
	case errors.Is(err, ErrInvalidAge):
		return status.Error(codes.InvalidArgument, err.Error())
	case errors.Is(err, ErrNameRequired):
		return status.Error(codes.InvalidArgument, err.Error())
	case errors.Is(err, ErrEmailAlreadyExist):
		return status.Error(codes.AlreadyExists, err.Error())
	default:
		return status.Error(codes.Internal, "internal error")
	}
}

// GetUser 获取用户
func (s *userServiceServer) GetUser(ctx context.Context, req *pb.GetUserRequest) (*pb.GetUserResponse, error) {
	log.Printf("[GetUser] request: id=%s", req.Id)

	// 显式验证
	if err := validateGetUser(req); err != nil {
		log.Printf("[GetUser] validation failed: %v", err)
		return nil, mapError(err)
	}

	user, err := s.store.Get(req.Id)
	if err != nil {
		log.Printf("[GetUser] store error: %v", err)
		return nil, mapError(err)
	}

	log.Printf("[GetUser] success: id=%s, name=%s", user.Id, user.Name)
	return &pb.GetUserResponse{User: user}, nil
}

// CreateUser 创建用户
func (s *userServiceServer) CreateUser(ctx context.Context, req *pb.CreateUserRequest) (*pb.CreateUserResponse, error) {
	log.Printf("[CreateUser] request: name=%s, email=%s, age=%d", req.Name, req.Email, req.Age)

	// 显式验证
	if err := validateCreateUser(req); err != nil {
		log.Printf("[CreateUser] validation failed: %v", err)
		return nil, mapError(err)
	}

	user, err := s.store.Create(req.Name, req.Email, req.Age, req.Phone)
	if err != nil {
		log.Printf("[CreateUser] store error: %v", err)
		return nil, mapError(err)
	}

	log.Printf("[CreateUser] success: id=%s", user.Id)
	return &pb.CreateUserResponse{User: user}, nil
}

// ListUsers 列出用户（支持分页和搜索）
func (s *userServiceServer) ListUsers(ctx context.Context, req *pb.ListUsersRequest) (*pb.ListUsersResponse, error) {
	log.Printf("[ListUsers] request: page=%d, page_size=%d, keyword=%q", req.Page, req.PageSize, req.Keyword)

	// 设置默认值
	page := req.GetPage()
	if page <= 0 {
		page = 1
	}
	pageSize := req.GetPageSize()
	if pageSize <= 0 {
		pageSize = 10
	}
	if pageSize > 100 {
		pageSize = 100
	}

	users, total, err := s.store.List(page, pageSize, req.Keyword)
	if err != nil {
		log.Printf("[ListUsers] store error: %v", err)
		return nil, mapError(err)
	}

	log.Printf("[ListUsers] success: total=%d, returned=%d", total, len(users))
	return &pb.ListUsersResponse{
		Users:    users,
		Total:    total,
		Page:     page,
		PageSize: pageSize,
	}, nil
}

// UpdateUser 更新用户
func (s *userServiceServer) UpdateUser(ctx context.Context, req *pb.UpdateUserRequest) (*pb.UpdateUserResponse, error) {
	log.Printf("[UpdateUser] request: id=%s, name=%s, email=%s, age=%d", req.Id, req.Name, req.Email, req.Age)

	// 显式验证
	if err := validateUpdateUser(req); err != nil {
		log.Printf("[UpdateUser] validation failed: %v", err)
		return nil, mapError(err)
	}

	user, err := s.store.Update(req.Id, req.Name, req.Email, req.Age, req.Phone)
	if err != nil {
		log.Printf("[UpdateUser] store error: %v", err)
		return nil, mapError(err)
	}

	log.Printf("[UpdateUser] success: id=%s", user.Id)
	return &pb.UpdateUserResponse{User: user}, nil
}

// DeleteUser 删除用户
func (s *userServiceServer) DeleteUser(ctx context.Context, req *pb.DeleteUserRequest) (*pb.DeleteUserResponse, error) {
	log.Printf("[DeleteUser] request: id=%s", req.Id)

	// 显式验证
	if err := validateDeleteUser(req); err != nil {
		log.Printf("[DeleteUser] validation failed: %v", err)
		return nil, mapError(err)
	}

	if err := s.store.Delete(req.Id); err != nil {
		log.Printf("[DeleteUser] store error: %v", err)
		return nil, mapError(err)
	}

	log.Printf("[DeleteUser] success: id=%s", req.Id)
	return &pb.DeleteUserResponse{
		Success: true,
		Message: fmt.Sprintf("user %s deleted", req.Id),
	}, nil
}

// loggingUnaryInterceptor 服务端日志拦截器
func loggingUnaryInterceptor(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
	start := time.Now()
	resp, err := handler(ctx, req)
	duration := time.Since(start)

	if err != nil {
		log.Printf("[Interceptor] %s FAILED: %v (duration=%v)", info.FullMethod, err, duration)
	} else {
		log.Printf("[Interceptor] %s SUCCESS (duration=%v)", info.FullMethod, duration)
	}
	return resp, err
}

// recoveryUnaryInterceptor 恢复 panic 的拦截器
func recoveryUnaryInterceptor(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp interface{}, err error) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("[Interceptor] PANIC recovered: method=%s, panic=%v", info.FullMethod, r)
			err = status.Error(codes.Internal, "internal server error")
		}
	}()
	return handler(ctx, req)
}

func main() {
	port := os.Getenv("GRPC_PORT")
	if port == "" {
		port = "50051"
	}

	lis, err := net.Listen("tcp", fmt.Sprintf(":%s", port))
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}
	defer lis.Close()

	// 初始化存储并插入测试数据
	store := newUserStore()
	seedTestData(store)

	// 创建 gRPC 服务器
	s := grpc.NewServer(
		grpc.ChainUnaryInterceptor(
			recoveryUnaryInterceptor,
			loggingUnaryInterceptor,
		),
	)
	pb.RegisterUserServiceServer(s, newUserServiceServer(store))

	// 注册反射服务（用于 grpcurl 等工具调试）
	reflection.Register(s)

	// 优雅关闭
	done := make(chan os.Signal, 1)
	signal.Notify(done, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-done
		log.Println("shutting down gRPC server gracefully...")
		s.GracefulStop()
	}()

	log.Printf("gRPC server listening on :%s", port)
	if err := s.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}

// seedTestData 插入测试数据
func seedTestData(store *userStore) {
	names := []string{"Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry", "Ivy", "Jack"}
	for _, name := range names {
		email := fmt.Sprintf("%s@example.com", name)
		_, err := store.Create(name, email, int32(20+rand.Intn(30)), fmt.Sprintf("138%08d", rand.Intn(100000000)))
		if err != nil {
			log.Printf("seed: failed to create user %s: %v", name, err)
		}
	}
	log.Printf("seeded %d test users", len(names))
}

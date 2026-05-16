package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	pb "examples/grpc-service/proto/user/v1"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

func main() {
	addr := os.Getenv("GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50051"
	}

	// 建立连接
	conn, err := grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithUnaryInterceptor(clientLoggingInterceptor),
	)
	if err != nil {
		log.Fatalf("failed to connect: %v", err)
	}
	defer conn.Close()

	client := pb.NewUserServiceClient(conn)
	ctx := context.Background()

	// 运行演示
	if err := runDemo(ctx, client); err != nil {
		log.Fatalf("demo failed: %v", err)
	}
}

// clientLoggingInterceptor 客户端日志拦截器
func clientLoggingInterceptor(ctx context.Context, method string, req, reply interface{}, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {
	start := time.Now()
	err := invoker(ctx, method, req, reply, cc, opts...)
	duration := time.Since(start)

	if err != nil {
		log.Printf("[Client] %s FAILED: %v (duration=%v)", method, err, duration)
	} else {
		log.Printf("[Client] %s SUCCESS (duration=%v)", method, duration)
	}
	return err
}

// printCode 打印 gRPC 状态码
func printCode(err error) string {
	if err == nil {
		return "OK"
	}
	st := status.Convert(err)
	return fmt.Sprintf("%s (code=%d)", st.Code().String(), st.Code())
}

func runDemo(ctx context.Context, client pb.UserServiceClient) error {
	fmt.Println("═══════════════════════════════════════════")
	fmt.Println("   Go gRPC User Service Demo")
	fmt.Println("═══════════════════════════════════════════")

	// 1. ListUsers - 列出所有用户
	fmt.Println("\n📋 1. ListUsers - 列出所有用户")
	listResp, err := client.ListUsers(ctx, &pb.ListUsersRequest{Page: 1, PageSize: 5})
	if err != nil {
		return fmt.Errorf("ListUsers failed: %w (code=%s)", err, printCode(err))
	}
	fmt.Printf("   总数: %d, 当前页: %d, 每页: %d\n", listResp.Total, listResp.Page, listResp.PageSize)
	for _, u := range listResp.Users {
		fmt.Printf("   - %s | %s | %s | age=%d\n", u.Id, u.Name, u.Email, u.Age)
	}

	// 2. CreateUser - 创建用户
	fmt.Println("\n📝 2. CreateUser - 创建新用户")
	createResp, err := client.CreateUser(ctx, &pb.CreateUserRequest{
		Name:  "TestUser",
		Email: "testuser@example.com",
		Age:   25,
		Phone: "13912345678",
	})
	if err != nil {
		return fmt.Errorf("CreateUser failed: %w (code=%s)", err, printCode(err))
	}
	newUser := createResp.User
	fmt.Printf("   创建成功: id=%s, name=%s, email=%s\n", newUser.Id, newUser.Name, newUser.Email)

	// 3. GetUser - 获取刚创建的用户
	fmt.Println("\n🔍 3. GetUser - 获取用户")
	getResp, err := client.GetUser(ctx, &pb.GetUserRequest{Id: newUser.Id})
	if err != nil {
		return fmt.Errorf("GetUser failed: %w (code=%s)", err, printCode(err))
	}
	u := getResp.User
	fmt.Printf("   获取成功: id=%s, name=%s, email=%s, age=%d, phone=%s\n",
		u.Id, u.Name, u.Email, u.Age, u.Phone)

	// 4. UpdateUser - 更新用户
	fmt.Println("\n✏️  4. UpdateUser - 更新用户")
	updateResp, err := client.UpdateUser(ctx, &pb.UpdateUserRequest{
		Id:    newUser.Id,
		Name:  "UpdatedUser",
		Email: "updated@example.com",
		Age:   30,
		Phone: "13987654321",
	})
	if err != nil {
		return fmt.Errorf("UpdateUser failed: %w (code=%s)", err, printCode(err))
	}
	u = updateResp.User
	fmt.Printf("   更新成功: id=%s, name=%s, email=%s, age=%d\n",
		u.Id, u.Name, u.Email, u.Age)

	// 5. 搜索用户
	fmt.Println("\n🔎 5. ListUsers - 搜索 'Alice'")
	searchResp, err := client.ListUsers(ctx, &pb.ListUsersRequest{
		Page:    1,
		PageSize: 10,
		Keyword: "Alice",
	})
	if err != nil {
		return fmt.Errorf("ListUsers search failed: %w (code=%s)", err, printCode(err))
	}
	fmt.Printf("   搜索结果: 共 %d 条\n", searchResp.Total)
	for _, u := range searchResp.Users {
		fmt.Printf("   - %s | %s | %s\n", u.Id, u.Name, u.Email)
	}

	// 6. 验证 - 创建重复 email
	fmt.Println("\n❌ 6. 验证错误处理 - 重复 email")
	_, err = client.CreateUser(ctx, &pb.CreateUserRequest{
		Name:  "DupUser",
		Email: "testuser@example.com", // 已存在的 email
		Age:   20,
	})
	fmt.Printf("   结果: code=%s\n", printCode(err))

	// 7. 验证 - 获取不存在的用户
	fmt.Println("\n❌ 7. 验证错误处理 - 不存在的用户")
	_, err = client.GetUser(ctx, &pb.GetUserRequest{Id: "nonexistent"})
	fmt.Printf("   结果: code=%s\n", printCode(err))

	// 8. 验证 - 无效参数
	fmt.Println("\n❌ 8. 验证错误处理 - 无效参数（name 为空）")
	_, err = client.CreateUser(ctx, &pb.CreateUserRequest{
		Name:  "",
		Email: "valid@example.com",
		Age:   20,
	})
	fmt.Printf("   结果: code=%s\n", printCode(err))

	// 9. DeleteUser - 删除用户
	fmt.Println("\n🗑️  9. DeleteUser - 删除用户")
	deleteResp, err := client.DeleteUser(ctx, &pb.DeleteUserRequest{Id: newUser.Id})
	if err != nil {
		return fmt.Errorf("DeleteUser failed: %w (code=%s)", err, printCode(err))
	}
	fmt.Printf("   删除成功: success=%v, message=%s\n", deleteResp.Success, deleteResp.Message)

	fmt.Println("\n═══════════════════════════════════════════")
	fmt.Println("   Demo Complete ✅")
	fmt.Println("═══════════════════════════════════════════")
	return nil
}
